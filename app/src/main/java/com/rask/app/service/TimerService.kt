package com.rask.app.service

import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.rask.app.R
import com.rask.app.RaskApplication
import com.rask.app.ui.main.MainActivity
import com.rask.app.utils.NotificationHelper
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Foreground stopwatch service.
 *
 * Lifecycle:
 *   - Started when user presses "Start timer" in QuickLog.
 *   - Stays alive (notification = "Timer running" with pause/stop controls).
 *   - Updates the notification text every second.
 *   - Pauses/resumes via intent actions [ACTION_PAUSE] / [ACTION_RESUME].
 *   - Stops via [ACTION_STOP] — saves the activity to DB and tears down.
 *
 * Persistence:
 *   - Timer start/pause/accumulated state is mirrored to DataStore so the
 *     service can be killed by the OS and re-hydrated when the user reopens
 *     the app.
 */
class TimerService : LifecycleService() {

    private var tickerJob: Job? = null
    private var paused = false

    override fun onBind(intent: Intent): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)

        when (intent?.action) {
            ACTION_START -> startTimer()
            ACTION_PAUSE -> pauseTimer()
            ACTION_RESUME -> resumeTimer()
            ACTION_STOP -> stopAndSave()
            else -> {
                // On cold restart — rehydrate from prefs
                rehydrateIfRunning()
            }
        }
        return START_STICKY
    }

    // ---------- State machine ----------

    private fun startTimer() {
        startForegroundWithNotification(buildNotification(0L, paused = false))
        startTicker()
    }

    private fun pauseTimer() {
        if (paused) return
        paused = true
        lifecycleScope.launch {
            val app = application as RaskApplication
            // Snapshot current elapsed and accumulate
            val startedIso = app.prefs.timerStartedAt.first()
            val pausedAt = com.rask.app.utils.DateUtils.nowUtcIso()
            val accumulated = app.prefs.timerAccumulatedMs.first()
            val delta = if (startedIso.isNotBlank()) {
                com.rask.app.utils.DateUtils.between(startedIso, pausedAt)
            } else 0L
            app.prefs.setTimerAccumulatedMs(accumulated + delta)
            app.prefs.setTimerPausedAt(pausedAt)
        }
        tickerJob?.cancel()
        // Update notification to reflect paused state
        lifecycleScope.launch {
            val total = currentTotalMs()
            notify(buildNotification(total, paused = true))
        }
    }

    private fun resumeTimer() {
        if (!paused) return
        paused = false
        lifecycleScope.launch {
            val app = application as RaskApplication
            // Reset start time to now; keep accumulated
            app.prefs.setTimerStartedAt(com.rask.app.utils.DateUtils.nowUtcIso())
            app.prefs.setTimerPausedAt("")
        }
        startTicker()
    }

    private fun stopAndSave() {
        lifecycleScope.launch {
            val app = application as RaskApplication
            val title = app.prefs.timerTitle.first().ifBlank { getString(R.string.app_name) }
            val category = app.prefs.timerCategory.first()
            val tag = app.prefs.timerTag.first()
            val startedIso = app.prefs.timerStartedAt.first()
            val endedIso = com.rask.app.utils.DateUtils.nowUtcIso()

            // Compute total duration
            val accumulated = app.prefs.timerAccumulatedMs.first()
            val delta = if (paused) {
                val pausedIso = app.prefs.timerPausedAt.first()
                if (pausedIso.isNotBlank() && startedIso.isNotBlank()) {
                    com.rask.app.utils.DateUtils.between(startedIso, pausedIso)
                } else 0L
            } else {
                if (startedIso.isNotBlank()) {
                    com.rask.app.utils.DateUtils.between(startedIso, endedIso)
                } else 0L
            }
            val totalMs = accumulated + delta

            // Only persist if meaningful (>1s)
            if (totalMs >= 1000L && startedIso.isNotBlank()) {
                app.activityRepo.logTimed(
                    title = title,
                    startedIso = startedIso,
                    endedIso = endedIso,
                    category = category,
                    tag = tag,
                    notes = null,
                    color = null
                )
                app.goalRepo.recomputeAll()
            }

            app.prefs.clearTimer()
            tickerJob?.cancel()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun rehydrateIfRunning() {
        lifecycleScope.launch {
            val app = application as RaskApplication
            val startedIso = app.prefs.timerStartedAt.first()
            if (startedIso.isBlank()) {
                stopSelf(); return@launch
            }
            paused = app.prefs.timerPausedAt.first().isNotBlank()
            startForegroundWithNotification(buildNotification(currentTotalMs(), paused))
            if (!paused) startTicker()
        }
    }

    private fun startTicker() {
        tickerJob?.cancel()
        tickerJob = lifecycleScope.launch {
            while (true) {
                if (!paused) {
                    val total = currentTotalMs()
                    notify(buildNotification(total, paused = false))
                }
                delay(1000)
            }
        }
    }

    // ---------- Helpers ----------

    private suspend fun currentTotalMs(): Long {
        val app = application as RaskApplication
        val accumulated = app.prefs.timerAccumulatedMs.first()
        val startedIso = app.prefs.timerStartedAt.first()
        if (paused) {
            val pausedIso = app.prefs.timerPausedAt.first()
            return if (startedIso.isNotBlank() && pausedIso.isNotBlank()) {
                accumulated + com.rask.app.utils.DateUtils.between(startedIso, pausedIso)
            } else accumulated
        }
        return if (startedIso.isNotBlank()) {
            accumulated + com.rask.app.utils.DateUtils.between(
                startedIso,
                com.rask.app.utils.DateUtils.nowUtcIso()
            )
        } else accumulated
    }

    private fun buildNotification(elapsedMs: Long, paused: Boolean): Notification {
        val label = if (paused) getString(R.string.home_timer_paused)
                    else getString(R.string.timer_notification_text)
        val display = com.rask.app.utils.DateUtils.millisToHhMmSs(elapsedMs)

        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPi = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val pauseIntent = Intent(this, TimerService::class.java).setAction(ACTION_PAUSE)
        val pausePi = PendingIntent.getService(
            this, 1, pauseIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val resumeIntent = Intent(this, TimerService::class.java).setAction(ACTION_RESUME)
        val resumePi = PendingIntent.getService(
            this, 2, resumeIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val stopIntent = Intent(this, TimerService::class.java).setAction(ACTION_STOP)
        val stopPi = PendingIntent.getService(
            this, 3, stopIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = NotificationCompat.Builder(this, NotificationHelper.CHANNEL_TIMER)
            .setSmallIcon(R.drawable.ic_history)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("$label · $display")
            .setOngoing(true)
            .setContentIntent(openPi)
            .setColor(0xD4AF37)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)

        if (paused) {
            builder.addAction(R.drawable.ic_play, getString(R.string.timer_resume), resumePi)
        } else {
            builder.addAction(R.drawable.ic_pause, getString(R.string.timer_pause), pausePi)
        }
        builder.addAction(R.drawable.ic_stop, getString(R.string.timer_stop), stopPi)

        return builder.build()
    }

    private fun startForegroundWithNotification(n: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NotificationHelper.NOTIF_TIMER_ID, n,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_STOPWATCH
            )
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NotificationHelper.NOTIF_TIMER_ID, n,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(NotificationHelper.NOTIF_TIMER_ID, n)
        }
    }

    private fun notify(n: Notification) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
        nm.notify(NotificationHelper.NOTIF_TIMER_ID, n)
    }

    companion object {
        const val ACTION_START = "com.rask.app.timer.START"
        const val ACTION_PAUSE = "com.rask.app.timer.PAUSE"
        const val ACTION_RESUME = "com.rask.app.timer.RESUME"
        const val ACTION_STOP = "com.rask.app.timer.STOP"

        fun start(context: Context) {
            val intent = Intent(context, TimerService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun pause(context: Context) {
            context.startService(Intent(context, TimerService::class.java).setAction(ACTION_PAUSE))
        }

        fun resume(context: Context) {
            context.startService(Intent(context, TimerService::class.java).setAction(ACTION_RESUME))
        }

        fun stop(context: Context) {
            context.startService(Intent(context, TimerService::class.java).setAction(ACTION_STOP))
        }
    }
}
