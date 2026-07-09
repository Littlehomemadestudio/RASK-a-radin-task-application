package com.rask.app.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.rask.app.R
import com.rask.app.RaskApplication
import com.rask.app.ui.main.MainActivity
import com.rask.app.ui.home.QuickLogActivity
import com.rask.app.utils.DateUtils
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Home-screen widget.
 *
 * Renders today's total time + a quick-log button.
 * Tapping the widget body opens MainActivity; tapping the FAB opens QuickLogActivity.
 *
 * Updated via [updateAll] (called by the activity repository after every insert)
 * and by WorkManager during the periodic widget refresh.
 */
class RaskWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        appWidgetIds.forEach { id ->
            updateOne(context, appWidgetManager, id)
        }
    }

    companion object {
        fun updateAll(context: Context) {
            val mgr = AppWidgetManager.getInstance(context)
            val ids = mgr.getAppWidgetIds(ComponentName(context, RaskWidgetProvider::class.java))
            ids.forEach { updateOne(context, mgr, it) }
        }

        private fun updateOne(
            context: Context,
            mgr: AppWidgetManager,
            id: Int
        ) {
            val views = RemoteViews(context.packageName, R.layout.widget_rask)

            // Body tap → open MainActivity
            val openIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            val openPi = PendingIntent.getActivity(
                context, 0, openIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            views.setOnClickPendingIntent(R.id.widgetTotal, openPi)

            // FAB tap → open QuickLogActivity
            val qlIntent = Intent(context, QuickLogActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            val qlPi = PendingIntent.getActivity(
                context, 1, qlIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            views.setOnClickPendingIntent(R.id.widgetQuickLog, qlPi)

            // Render today's total asynchronously
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val app = context.applicationContext as RaskApplication
                    val range = DateUtils.todayRange()
                    val total = app.activityRepo.totalInRange(range)
                    views.setTextViewText(
                        R.id.widgetTotal,
                        if (total > 0) DateUtils.durationLabel(total)
                        else context.getString(R.string.widget_no_data)
                    )
                    mgr.updateAppWidget(id, views)
                } catch (_: Throwable) {
                    // Widget may update before app is fully initialized — silent fail
                }
            }
        }
    }
}
