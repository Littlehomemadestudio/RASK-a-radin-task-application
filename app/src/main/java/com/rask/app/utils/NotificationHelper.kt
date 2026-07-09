package com.rask.app.utils

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationManagerCompat

/**
 * Tiny notification channel helper.
 *
 * Two channels:
 *   - "timer"     — low-priority, used by the foreground TimerService
 *   - "reminders" — default-priority, used by goal reminders
 */
object NotificationHelper {

    const val CHANNEL_TIMER = "rask.channel.timer"
    const val CHANNEL_REMINDERS = "rask.channel.reminders"

    const val NOTIF_TIMER_ID = 1001
    const val NOTIF_REMINDER_ID = 1002

    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_TIMER,
                context.getString(com.rask.app.R.string.channel_timer),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Active stopwatch — low priority, no sound"
                setShowBadge(false)
            }
        )

        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_REMINDERS,
                context.getString(com.rask.app.R.string.channel_reminders),
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Gentle reminders when behind on a goal"
            }
        )
    }

    fun areNotificationsEnabled(context: Context): Boolean =
        NotificationManagerCompat.from(context).areNotificationsEnabled()
}
