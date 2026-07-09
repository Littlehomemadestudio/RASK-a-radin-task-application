package com.rask.app.utils

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.rask.app.R
import com.rask.app.ui.main.MainActivity

/**
 * Posts a gentle reminder notification.
 *
 * Kept as a tiny singleton object to keep NotificationHelper focused on channels.
 */
object ReminderNotifier {

    fun notify(context: Context, title: String, remaining: String) {
        val openIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pi = PendingIntent.getActivity(
            context, 0, openIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val text = context.getString(R.string.goals_reminder_text, remaining, title)

        val n = NotificationCompat.Builder(context, NotificationHelper.CHANNEL_REMINDERS)
            .setSmallIcon(R.drawable.ic_goals)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .setColor(0xD4AF37)
            .build()

        try {
            NotificationManagerCompat.from(context)
                .notify(NotificationHelper.NOTIF_REMINDER_ID, n)
        } catch (_: SecurityException) {
            // POST_NOTIFICATIONS not granted on Android 13+ — silent fail.
        }
    }
}
