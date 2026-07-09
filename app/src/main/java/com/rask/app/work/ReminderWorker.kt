package com.rask.app.work

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.rask.app.RaskApplication
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import java.util.concurrent.TimeUnit

/**
 * Schedules a daily check that fires a gentle reminder if the user is behind
 * on any daily goal. Honors the user's preferred reminder time.
 *
 * Implementation: a periodic WorkManager job with a 24h interval. We could
 * use exact alarms instead, but WorkManager respects doze + battery saver
 * and gives the user predictable behaviour without extra permissions.
 */
object ReminderScheduler {

    private const val WORK_NAME = "rask.daily_reminder"

    fun scheduleIfEnabled(context: Context) {
        val app = context.applicationContext as RaskApplication
        val prefs = app.prefs

        // Read once synchronously to decide whether to schedule.
        // Acceptable at app-startup / boot — this receiver runs on a background thread.
        val enabled = runBlocking { prefs.remindersEnabled.first() }
        val hour = runBlocking { prefs.reminderHour.first() }
        val minute = runBlocking { prefs.reminderMinute.first() }

        if (!enabled) {
            cancel(context)
            return
        }

        val now = java.util.Calendar.getInstance()
        val target = java.util.Calendar.getInstance().apply {
            set(java.util.Calendar.HOUR_OF_DAY, hour)
            set(java.util.Calendar.MINUTE, minute)
            set(java.util.Calendar.SECOND, 0)
            set(java.util.Calendar.MILLISECOND, 0)
            if (timeInMillis <= now.timeInMillis) {
                add(java.util.Calendar.DAY_OF_MONTH, 1)
            }
        }
        val initialDelay = target.timeInMillis - now.timeInMillis

        val req = PeriodicWorkRequestBuilder<ReminderWorker>(
            24, TimeUnit.HOURS,
            15, TimeUnit.MINUTES
        )
            .setInitialDelay(initialDelay, TimeUnit.MILLISECONDS)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.NOT_REQUIRED)
                    .build()
            )
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            req
        )
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
    }
}

class ReminderWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as RaskApplication
        val goals = app.goalRepo.all().filter {
            it.active && it.scope == com.rask.app.data.db.entity.GoalEntity.SCOPE_DAILY
        }
        if (goals.isEmpty()) return Result.success()

        // Find any daily goal that is behind target
        for (goal in goals) {
            val progress = app.goalRepo.progressFor(goal)
            if (progress < goal.targetMillis) {
                val remaining = goal.targetMillis - progress
                val remainingLabel = com.rask.app.utils.DateUtils.durationLabel(remaining)
                val goalName = goal.name
                    ?: goal.categoryId?.let { cid -> app.categoryRepo.byId(cid)?.name }
                    ?: "Daily"

                com.rask.app.utils.ReminderNotifier.notify(
                    context = applicationContext,
                    title = goalName,
                    remaining = remainingLabel
                )
                break // one reminder per day is plenty
            }
        }
        return Result.success()
    }
}
