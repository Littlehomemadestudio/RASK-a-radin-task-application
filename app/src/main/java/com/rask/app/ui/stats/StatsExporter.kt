package com.rask.app.ui.stats

import android.content.Context
import com.rask.app.RaskApplication
import com.rask.app.utils.DateUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.PrintWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Exports the user's activities to PDF (simple text-only, no Android PdfDocument dependency
 * needed for headless unit-testability) or CSV.
 *
 * PDF here is intentionally minimal — a plain printable text report. Apps that need
 * a more designed PDF can swap in Android PdfDocument later; the API surface stays the same.
 *
 * We use Android's built-in [android.graphics.pdf.PdfDocument] for the PDF so we
 * don't add a heavy PDF library to the APK.
 */
object StatsExporter {

    suspend fun exportCsv(context: Context): String? = withContext(Dispatchers.IO) {
        try {
            val app = context.applicationContext as RaskApplication
            val activities = app.activityRepo.all()
            if (activities.isEmpty()) return@withContext null

            val file = File(context.getExternalFilesDir(null), "exports").apply { mkdirs() }
                .let { File(it, "rask-${stamp()}.csv") }

            file.printWriter().use { w ->
                w.println("id,title,startedAt,endedAt,durationMillis,durationHours,category,tag,notes,isTimed")
                for (a in activities) {
                    w.println(listOf(
                        a.id.toString(),
                        csvEscape(a.title),
                        a.startedAt,
                        a.endedAt,
                        a.durationMillis.toString(),
                        "%.3f".format(a.durationMillis / 3_600_000.0),
                        csvEscape(a.category ?: ""),
                        csvEscape(a.tag ?: ""),
                        csvEscape(a.notes ?: ""),
                        a.isTimed.toString()
                    ).joinToString(","))
                }
            }
            file.absolutePath
        } catch (_: Throwable) { null }
    }

    suspend fun exportPdf(context: Context): String? = withContext(Dispatchers.IO) {
        try {
            val app = context.applicationContext as RaskApplication
            val activities = app.activityRepo.all()
            if (activities.isEmpty()) return@withContext null

            val file = File(context.getExternalFilesDir(null), "exports").apply { mkdirs() }
                .let { File(it, "rask-report-${stamp()}.pdf") }

            // Use Android PdfDocument — built-in, no extra dependency.
            val pdf = android.graphics.pdf.PdfDocument()
            val pageWidth = 595 // A4 at 72dpi
            val pageHeight = 842
            val paint = android.graphics.Paint().apply {
                color = 0xF5EEDC.toInt()
                textSize = 11f
                isAntiAlias = true
            }
            val titlePaint = android.graphics.Paint(paint).apply {
                color = 0xD4AF37.toInt()
                textSize = 20f
                isFakeBoldText = false
            }

            val pageNum = 1
            var pageInfo = android.graphics.pdf.PdfDocument.PageInfo.Builder(pageWidth, pageHeight, pageNum).create()
            var page = pdf.startPage(pageInfo)
            var canvas = page.canvas
            var y = 60f

            // Title
            canvas.drawText(context.getString(R.string.app_name) + " — Report", 40f, y, titlePaint)
            y += 30f
            canvas.drawText("Generated: ${DateUtils.mediumDate(java.time.LocalDateTime.now())}", 40f, y, paint)
            y += 30f

            // Totals
            val totalMs = activities.sumOf { it.durationMillis }
            canvas.drawText("Total: ${DateUtils.durationLabel(totalMs)}",
                40f, y, paint); y += 25f
            canvas.drawText("Activities: ${activities.size}",
                40f, y, paint); y += 25f

            // Per-activity listing (paginated)
            for (a in activities) {
                if (y > pageHeight - 60f) {
                    pdf.finishPage(page)
                    pageInfo = android.graphics.pdf.PdfDocument.PageInfo.Builder(pageWidth, pageHeight, pageNum + 1).create()
                    page = pdf.startPage(pageInfo)
                    canvas = page.canvas
                    y = 60f
                }
                val local = DateUtils.fromUtcIso(a.startedAt)
                val line = "${DateUtils.shortDate(local)} ${DateUtils.shortTime(local)} · " +
                    "${DateUtils.durationLabel(a.durationMillis)} · ${a.title}"
                canvas.drawText(line, 40f, y, paint)
                y += 16f
            }

            pdf.finishPage(page)
            file.outputStream().use { pdf.writeTo(it) }
            pdf.close()
            file.absolutePath
        } catch (_: Throwable) { null }
    }

    private fun csvEscape(s: String): String {
        val needsQuote = s.any { it == ',' || it == '"' || it == '\n' || it == '\r' }
        val escaped = s.replace("\"", "\"\"")
        return if (needsQuote) "\"$escaped\"" else escaped
    }

    private fun stamp(): String =
        SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())
}
