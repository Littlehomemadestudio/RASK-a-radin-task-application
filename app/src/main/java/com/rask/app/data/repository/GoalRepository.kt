package com.rask.app.data.repository

import com.rask.app.data.db.RaskDatabase
import com.rask.app.data.db.entity.GoalEntity
import com.rask.app.data.db.entity.StreakEntity
import com.rask.app.utils.DateUtils
import kotlinx.coroutines.flow.Flow

/**
 * Goal + Streak repository.
 *
 * Streaks are recomputed lazily — see [recomputeStreaksFor] — because doing it
 * on every tick would be wasteful. We recompute on app open and after every
 * activity insert.
 */
class GoalRepository(
    private val db: RaskDatabase,
    private val activityRepo: ActivityRepository
) {

    private val goalDao = db.goalDao()
    private val streakDao = db.streakDao()

    fun observeActive(): Flow<List<GoalEntity>> = goalDao.observeActive()
    fun observeAll(): Flow<List<GoalEntity>> = goalDao.observeAll()

    suspend fun all(): List<GoalEntity> = goalDao.all()
    suspend fun byId(id: Long): GoalEntity? = goalDao.byId(id)

    suspend fun upsert(goal: GoalEntity): Long = goalDao.insert(goal)
    suspend fun update(goal: GoalEntity) = goalDao.update(goal)
    suspend fun delete(id: Long) = goalDao.deleteById(id)

    // ---------- Progress ----------

    /**
     * How much of this goal has been hit in the current period.
     * Returns millis achieved (may exceed [GoalEntity.targetMillis]).
     */
    suspend fun progressFor(goal: GoalEntity): Long {
        val range = when (goal.scope) {
            GoalEntity.SCOPE_DAILY -> DateUtils.todayRange()
            GoalEntity.SCOPE_WEEKLY -> DateUtils.thisWeekRange()
            GoalEntity.SCOPE_MONTHLY -> DateUtils.thisMonthRange()
            else -> DateUtils.todayRange()
        }
        val categoryName = goal.categoryId?.let { cid ->
            db.categoryDao().byId(cid)?.name
        }
        return activityRepo.totalInRange(range, category = categoryName, tag = null)
    }

    /**
     * Did the user hit the goal for the *current* period?
     * Used for streak increments.
     */
    suspend fun hitThisPeriod(goal: GoalEntity): Boolean =
        progressFor(goal) >= goal.targetMillis

    /**
     * Did the user hit the goal for the *previous* period?
     * (For weekly/monthly, this is the immediately preceding week/month.)
     */
    suspend fun hitPreviousPeriod(goal: GoalEntity): Boolean {
        // Compute the previous-period range and total
        val today = java.time.LocalDate.now()
        val range = when (goal.scope) {
            GoalEntity.SCOPE_DAILY -> {
                val y = today.minusDays(1)
                DateUtils.customRange(y, y)
            }
            GoalEntity.SCOPE_WEEKLY -> {
                val monday = today.with(java.time.temporal.TemporalAdjusters.previousOrSame(java.time.DayOfWeek.MONDAY))
                val prevMonday = monday.minusDays(7)
                DateUtils.customRange(prevMonday, prevMonday.plusDays(6))
            }
            GoalEntity.SCOPE_MONTHLY -> {
                val ym = java.time.YearMonth.of(today.year, today.month).minusMonths(1)
                DateUtils.customRange(ym.atDay(1), ym.atEndOfMonth())
            }
            else -> DateUtils.todayRange()
        }
        val categoryName = goal.categoryId?.let { db.categoryDao().byId(it)?.name }
        val total = activityRepo.totalInRange(range, category = categoryName, tag = null)
        return total >= goal.targetMillis
    }

    // ---------- Streaks ----------

    /**
     * Recompute the current streak for a goal.
     *
     * Strategy: walk backwards from the current period. The current period
     * only counts if it has already hit the goal; we then count previous
     * consecutive periods that hit.
     */
    suspend fun recomputeStreaksFor(goal: GoalEntity) {
        var current = 0
        if (hitThisPeriod(goal)) current = 1
        if (current == 1) {
            // walk back
            var cont = true
            var safety = 0
            while (cont && safety < 10000) {
                safety++
                // Walk by checking the previous period relative to a moving pointer.
                // We do this by temporarily adjusting LocalDate.
                // (Reuses hitPreviousPeriod which is fixed to "today-1 period" — for
                // streaks deeper than 1 we need a pointer-based approach.)
                cont = false
            }
            // For simplicity and correctness, we use a separate function for deep streaks.
            current = deepCurrentStreak(goal)
        }

        val best = streakDao.byGoal(goal.id)?.best ?: 0
        val newBest = maxOf(best, current)
        val entity = StreakEntity(
            goalId = goal.id,
            current = current,
            best = newBest,
            lastHitAt = if (current > 0) DateUtils.nowUtcIso() else null,
            updatedAt = System.currentTimeMillis()
        )
        streakDao.upsert(entity)
    }

    /**
     * Walk backwards from today to compute the true current streak.
     * Caps at 10000 iterations for safety.
     */
    private suspend fun deepCurrentStreak(goal: GoalEntity): Int {
        if (!hitThisPeriod(goal)) return 0
        var streak = 1
        val today = java.time.LocalDate.now()
        for (i in 1 until 10000) {
            val pointer = when (goal.scope) {
                GoalEntity.SCOPE_DAILY -> today.minusDays(i.toLong())
                GoalEntity.SCOPE_WEEKLY -> today.minusWeeks(i.toLong())
                    .with(java.time.temporal.TemporalAdjusters.previousOrSame(java.time.DayOfWeek.MONDAY))
                GoalEntity.SCOPE_MONTHLY -> today.minusMonths(i.toLong())
                else -> today.minusDays(i.toLong())
            }
            val range = when (goal.scope) {
                GoalEntity.SCOPE_DAILY -> DateUtils.customRange(pointer, pointer)
                GoalEntity.SCOPE_WEEKLY -> DateUtils.customRange(pointer, pointer.plusDays(6))
                GoalEntity.SCOPE_MONTHLY -> {
                    val ym = java.time.YearMonth.of(pointer.year, pointer.month)
                    DateUtils.customRange(ym.atDay(1), ym.atEndOfMonth())
                }
                else -> DateUtils.customRange(pointer, pointer)
            }
            val categoryName = goal.categoryId?.let { db.categoryDao().byId(it)?.name }
            val total = activityRepo.totalInRange(range, category = categoryName, tag = null)
            if (total >= goal.targetMillis) streak++ else break
        }
        return streak
    }

    suspend fun streakFor(goalId: Long): StreakEntity? = streakDao.byGoal(goalId)
    fun observeStreaks(): Flow<List<StreakEntity>> = streakDao.observeAll()
    suspend fun allStreaks(): List<StreakEntity> = streakDao.all()

    /**
     * Recompute all active goal streaks. Run on app open + after activity insert.
     */
    suspend fun recomputeAll() {
        val active = goalDao.all().filter { it.active }
        active.forEach { recomputeStreaksFor(it) }
    }
}
