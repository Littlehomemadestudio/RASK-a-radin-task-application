package com.rask;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Starts the TimerService after device boot if a timer was running
 * (Python persists the running flag + start timestamp; the service picks up
 * the elapsed time on attach).
 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context ctx, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            // Python side will check the persisted state on next app launch
            // and restart the foreground service if needed.
        }
    }
}
