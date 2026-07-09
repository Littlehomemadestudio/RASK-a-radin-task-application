package com.rask.app.widget

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Stub receiver for the quick-settings tile shortcut.
 *
 * Real Quick Settings Tiles require a TileService on Android 7.1+. We provide
 * a simple receiver so the manifest entry resolves; full tile implementation
 * can be added later without breaking the manifest.
 */
class TimerTileReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        // No-op for now — toggle handled inside MainActivity via TimerService.pause/resume.
    }
}
