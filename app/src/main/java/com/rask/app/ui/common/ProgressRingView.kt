package com.rask.app.ui.common

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import androidx.core.content.ContextCompat
import com.rask.app.R

/**
 * Lightweight custom progress ring (no Lottie, no MPAndroidChart dependency).
 *
 * Draws:
 *  - a thin background ring in [rask_card_border]
 *  - a thicker foreground arc in [rask_gold] sweeping clockwise from top,
 *    scaled by [progress] (0..1).
 *
 * Used for the today hero card and per-goal progress.
 */
class ProgressRingView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var progress: Float = 0f
    private var ringThicknessBg: Float = 6f
    private var ringThicknessFg: Float = 6f
    private var startAngle: Float = -90f

    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        color = ContextCompat.getColor(context, R.color.rask_card_border)
    }
    private val fgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        color = ContextCompat.getColor(context, R.color.rask_gold)
    }
    private val rect = RectF()

    init {
        val density = resources.displayMetrics.density
        ringThicknessBg *= density
        ringThicknessFg *= density
        bgPaint.strokeWidth = ringThicknessBg
        fgPaint.strokeWidth = ringThicknessFg
    }

    fun setProgress(p: Float) {
        progress = p.coerceIn(0f, 1f)
        invalidate()
    }

    fun setThicknessDp(dp: Float) {
        val px = dp * resources.displayMetrics.density
        bgPaint.strokeWidth = px
        fgPaint.strokeWidth = px
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val pad = maxOf(bgPaint.strokeWidth, fgPaint.strokeWidth) / 2f + 4f
        rect.set(pad, pad, width - pad, height - pad)
        canvas.drawArc(rect, 0f, 360f, false, bgPaint)
        if (progress > 0f) {
            canvas.drawArc(rect, startAngle, 360f * progress, false, fgPaint)
        }
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val defaultSize = (96 * resources.displayMetrics.density).toInt()
        val width = resolveSize(defaultSize, widthMeasureSpec)
        val height = resolveSize(defaultSize, heightMeasureSpec)
        val size = minOf(width, height)
        setMeasuredDimension(size, size)
    }
}
