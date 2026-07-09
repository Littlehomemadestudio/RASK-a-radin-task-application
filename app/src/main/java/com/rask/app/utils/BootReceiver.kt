package com.rask.app.utils

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.WorkManager
import com.rask.app.RaskApplication
import com.rask.app.work.ReminderScheduler

/**
 * Re-arm reminder work after device reboot or app upgrade.
 *
 * We don't immediately fire a reminder — we just re-register the periodic
 * WorkManager job, since WorkManager's state is wiped on reboot.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED &&
            intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return

        // Use a background thread — receivers must return quickly
        Thread {
            val app = context.applicationContext as RaskApplication
            ReminderScheduler.scheduleIfEnabled(app)
        }.start()
    }
}
