package com.rask.app.ui.home

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.viewModelScope
import com.rask.app.RaskApplication
import com.rask.app.data.db.entity.ActivityEntity
import com.rask.app.data.db.entity.GoalEntity
import com.rask.app.utils.DateUtils
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Home-screen view model.
 *
 * Exposes:
 *   - today's total (LiveData<Long>)
 *   - today's activities (for the recent list)
 *   - active goals + their progress (List<GoalProgress>)
 *   - timer state (running / paused / elapsed)
 */
class HomeViewModel(app: Application) : AndroidViewModel(app) {

    private val raskApp = app as RaskApplication

    private val _todayTotal = MutableLiveData<Long>(0L)
    val todayTotal: LiveData<Long> = _todayTotal

    private val _todayTarget = MutableLiveData<Long>(0L)
    val todayTarget: LiveData<Long> = _todayTarget

    private val _recent = MutableLiveData<List<ActivityEntity>>(emptyList())
    val recent: LiveData<List<ActivityEntity>> = _recent

    private val _goalProgress = MutableLiveData<List<GoalProgress>>(emptyList())
    val goalProgress: LiveData<List<GoalProgress>> = _goalProgress

    private val _timerElapsed = MutableLiveData(0L)
    val timerElapsed: LiveData<Long> = _timerElapsed

    private val _timerPaused = MutableLiveData(false)
    val timerPaused: LiveData<Boolean> = _timerPaused

    private val _timerRunning = MutableLiveData(false)
    val timerRunning: LiveData<Boolean> = _timerRunning

    init {
        observeToday()
        observeGoals()
        observeTimer()
    }

    private fun observeToday() {
        viewModelScope.launch {
            raskApp.activityRepo.observeToday().collectLatest { acts ->
                _recent.value = acts.take(10)
                _todayTotal.value = acts.sumOf { it.durationMillis }
            }
        }
    }

    private fun observeGoals() {
        viewModelScope.launch {
            raskApp.goalRepo.observeActive().collectLatest { goals ->
                val dailyGoals = goals.filter { it.scope == GoalEntity.SCOPE_DAILY }
                _todayTarget.value = dailyGoals.firstOrNull()?.targetMillis ?: 0L

                val progressList = goals.take(6).map { g ->
                    val progress = raskApp.goalRepo.progressFor(g)
                    val ratio = if (g.targetMillis > 0)
                        (progress.toFloat() / g.targetMillis.toFloat()).coerceIn(0f, 1f)
                    else 0f
                    val streak = raskApp.goalRepo.streakFor(g.id)
                    GoalProgress(
                        goal = g,
                        progressMillis = progress,
                        ratio = ratio,
                        streak = streak?.current ?: 0
                    )
                }
                _goalProgress.value = progressList
            }
        }
    }

    private fun observeTimer() {
        viewModelScope.launch {
            raskApp.prefs.timerStartedAt.collectLatest { started ->
                if (started.isBlank()) {
                    _timerRunning.value = false
                    _timerElapsed.value = 0L
                    _timerPaused.value = false
                } else {
                    _timerRunning.value = true
                    refreshTimer()
                }
            }
        }
        viewModelScope.launch {
            raskApp.prefs.timerPausedAt.collectLatest {
                _timerPaused.value = it.isNotBlank()
                refreshTimer()
            }
        }
    }

    private fun refreshTimer() {
        viewModelScope.launch {
            val startedIso = raskApp.prefs.timerStartedAt.first()
            val pausedIso = raskApp.prefs.timerPausedAt.first()
            val accumulated = raskApp.prefs.timerAccumulatedMs.first()
            if (startedIso.isBlank()) {
                _timerElapsed.value = 0L
                return@launch
            }
            val delta = if (pausedIso.isNotBlank()) {
                DateUtils.between(startedIso, pausedIso)
            } else {
                DateUtils.between(startedIso, DateUtils.nowUtcIso())
            }
            _timerElapsed.value = accumulated + delta
        }
    }

    data class GoalProgress(
        val goal: GoalEntity,
        val progressMillis: Long,
        val ratio: Float,
        val streak: Int
    )
}
