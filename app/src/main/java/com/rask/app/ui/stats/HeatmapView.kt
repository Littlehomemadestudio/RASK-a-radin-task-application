package com.rask.app.ui.stats

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import androidx.core.content.ContextCompat
import com.rask.app.R
import com.rask.app.data.db.dao.DayTotal
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters

/**
 * GitHub-style activity heatmap.
 *
 * Renders up to ~52 weeks (≈ 1 year) of daily activity intensity, columns =
 * weeks (Mon→Sun vertically). 5 intensity buckets from rask_heat_0..rask_heat_4.
 *
 * Density auto-scales: this month view uses the longest month range we have;
 * if the user's range is shorter (e.g. today), we still show the full current
 * year so the heatmap reads as a continuous artifact.
 */
class HeatmapView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    private var data: Map<String, Long> = emptyMap() // day-bucket → millis

    private val cellSize: Float
    private val gap: Float
    private val leftPad: Float
    private val topPad: Float
    private val labelPaint: Paint
    private val cellPaint: Paint
    private val colors: List<Int>

    init {
        val d = resources.displayMetrics.density
        cellSize = 12f * d
        gap = 3f * d
        leftPad = 24f * d
        topPad = 12f * d
        labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = ContextCompat.getColor(context, R.color.rask_gray)
            textSize = 9f * d
            textAlign = Paint.Align.LEFT
        }
        cellPaint = Paint(Paint.ANTI_ALIAS_FLAG)
        colors = listOf(
            ContextCompat.getColor(context, R.color.rask_heat_0),
            ContextCompat.getColor(context, R.color.rask_heat_1),
            ContextCompat.getColor(context, R.color.rask_heat_2),
            ContextCompat.getColor(context, R.color.rask_heat_3),
            ContextCompat.getColor(context, R.color.rask_heat_4)
        )
    }

    fun setData(totals: List<DayTotal>) {
        data = totals.associate { it.day to it.totalMillis }
        requestLayout()
        invalidate()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredWidth = MeasureSpec.getSize(widthMeasureSpec)
        // 7 rows (days) + label row at top
        val rows = 7
        val desiredHeight = (topPad + rows * (cellSize + gap) + 4f).toInt()
        setMeasuredDimension(desiredWidth, resolveSize(desiredHeight, heightMeasureSpec))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        // Find a Sunday-aligned start date ~52 weeks ago
        val today = LocalDate.now()
        val start = today.minusWeeks(52).with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))

        // Determine max value in data for bucketing
        val max = data.values.maxOrNull() ?: 0L

        // Compute weeks to render: from start until today's week inclusive
        val endWeekStart = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        val weeks = mutableListOf<LocalDate>()
        var cursor = start
        while (!cursor.isAfter(endWeekStart)) {
            weeks.add(cursor)
            cursor = cursor.plusWeeks(1)
        }

        // Day-of-week labels (Mon, Wed, Fri)
        val dowLabels = mapOf(
            DayOfWeek.MONDAY to "M",
            DayOfWeek.WEDNESDAY to "W",
            DayOfWeek.FRIDAY to "F"
        )

        // Width-per-cell
        val availableWidth = width - leftPad - paddingLeft - paddingRight
        val cellWidth = (availableWidth - (weeks.size - 1) * gap) / weeks.size
        val cw = cellWidth.coerceAtLeast(cellSize)

        // Draw labels
        for ((dow, label) in dowLabels) {
            val y = topPad + (dow.ordinal) * (cellSize + gap) + cellSize * 0.75f
            canvas.drawText(label, 4f, y, labelPaint)
        }

        // Draw cells
        for ((wIdx, weekStart) in weeks.withIndex()) {
            for (dowIdx in 0..6) {
                val day = weekStart.plusDays(dowIdx.toLong())
                if (day.isAfter(today)) continue
                val bucket = day.toString()
                val total = data[bucket] ?: 0L
                val color = if (max > 0 && total > 0) {
                    val ratio = total.toFloat() / max.toFloat()
                    when {
                        ratio < 0.25f -> colors[1]
                        ratio < 0.5f -> colors[2]
                        ratio < 0.75f -> colors[3]
                        else -> colors[4]
                    }
                } else colors[0]

                cellPaint.color = color
                val left = leftPad + wIdx * (cw + gap)
                val top = topPad + dowIdx * (cellSize + gap)
                val rect = RectF(left, top, left + cw, top + cellSize)
                canvas.drawRoundRect(rect, 2f, 2f, cellPaint)
            }
        }
    }
}
