package com.rask;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Receives the daily goal-reminder alarm and forwards it to the Python side
 * via a content broadcast that Python (registered via jnius) listens for.
 *
 * For simplicity, this implementation just relaunches the main activity
 * (which causes Python to call reminders.maybe_fire_reminder() on resume).
 */
public class ReminderReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context ctx, Intent intent) {
        // The actual reminder firing happens in Python (services/reminders.py)
        // when this broadcast is received — wiring it up requires a
        // Python-side BroadcastReceiver registered via jnius.
        //
        // For now, just relaunch the app.
        Intent launch = ctx.getPackageManager()
            .getLaunchIntentForPackage(ctx.getPackageName());
        if (launch != null) {
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            launch.putExtra("fire_reminder", true);
            ctx.startActivity(launch);
        }
    }
}
