package com.rask.app.ui.goals

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.viewModelScope
import com.rask.app.RaskApplication
import com.rask.app.data.db.entity.GoalEntity
import com.rask.app.data.db.entity.StreakEntity
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class GoalsViewModel(app: Application) : AndroidViewModel(app) {

    private val raskApp = app as RaskApplication

    private val _goals = MutableLiveData<List<GoalEntity>>(emptyList())
    val goals: LiveData<List<GoalEntity>> = _goals

    private val _streaks = MutableLiveData<Map<Long, StreakEntity>>(emptyMap())
    val streaks: LiveData<Map<Long, StreakEntity>> = _streaks

    private val _progress = MutableLiveData<Map<Long, Long>>(emptyMap())
    val progress: LiveData<Map<Long, Long>> = _progress

    init {
        viewModelScope.launch {
            raskApp.goalRepo.observeAll().collectLatest { list ->
                _goals.value = list.filter { it.active }
                recompute()
            }
        }
    }

    fun recompute() {
        viewModelScope.launch {
            val list = _goals.value ?: return@launch
            val progressMap = mutableMapOf<Long, Long>()
            val streakMap = mutableMapOf<Long, StreakEntity>()
            for (g in list) {
                progressMap[g.id] = raskApp.goalRepo.progressFor(g)
                raskApp.goalRepo.streakFor(g.id)?.let { streakMap[g.id] = it }
            }
            _progress.value = progressMap
            _streaks.value = streakMap
        }
    }

    fun addGoal(scope: String, targetMillis: Long, categoryId: Long?, name: String?) {
        viewModelScope.launch {
            raskApp.goalRepo.upsert(
                GoalEntity(
                    scope = scope,
                    targetMillis = targetMillis,
                    categoryId = categoryId,
                    name = name
                )
            )
        }
    }

    fun deleteGoal(id: Long) {
        viewModelScope.launch {
            raskApp.goalRepo.delete(id)
        }
    }
}
