package com.rask;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Receives Pause / Stop button taps from the timer notification.
 *
 * Forwards the action into the Python process via a broadcast Intent that
 * the Python side can listen for (via jnius / BroadcastReceiver registered
 * from Python), or directly calls a static callback if Python registered one.
 *
 * For simplicity, we just relaunch the main activity with the action.
 */
public class TimerActionReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (action == null) return;

        Intent svc;
        if (action.equals("com.rask.TIMER_STOP")) {
            svc = new Intent(context, TimerService.class);
            context.stopService(svc);
            // TODO: trigger Python-side stop_and_save() via pyjnius broadcast
        } else if (action.equals("com.rask.TIMER_PAUSE")) {
            // TODO: trigger Python-side pause() via pyjnius broadcast
        }
    }
}
