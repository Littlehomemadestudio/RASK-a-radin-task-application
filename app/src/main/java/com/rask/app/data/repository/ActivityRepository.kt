package com.rask.app.data.repository

import com.rask.app.data.db.RaskDatabase
import com.rask.app.data.db.dao.CategoryTotal
import com.rask.app.data.db.dao.DayTotal
import com.rask.app.data.db.dao.DowTotal
import com.rask.app.data.db.dao.HourTotal
import com.rask.app.data.db.dao.LabelTotal
import com.rask.app.data.db.entity.ActivityEntity
import com.rask.app.utils.DateUtils
import com.rask.app.utils.DateUtils.IsoRange
import kotlinx.coroutines.flow.Flow
import java.time.LocalDateTime

/**
 * Activity repository — the only place the UI should talk to for activity data.
 *
 * Sits on top of [RaskDatabase.activityDao] and adds domain convenience
 * (range helpers, vo conversion, etc).
 */
class ActivityRepository(private val db: RaskDatabase) {

    private val dao = db.activityDao()

    // ---------- Inserts / updates ----------

    suspend fun logManual(
        title: String,
        startedAt: LocalDateTime,
        endedAt: LocalDateTime,
        category: String?,
        tag: String?,
        notes: String?,
        color: String?
    ): Long {
        val entity = ActivityEntity.create(
            title = title,
            startedAt = startedAt,
            endedAt = endedAt,
            category = category,
            tag = tag,
            notes = notes,
            color = color,
            isTimed = false
        )
        return dao.insert(entity)
    }

    suspend fun logTimed(
        title: String,
        startedIso: String,
        endedIso: String,
        category: String?,
        tag: String?,
        notes: String?,
        color: String?
    ): Long {
        val started = DateUtils.fromUtcIso(startedIso)
        val ended = DateUtils.fromUtcIso(endedIso)
        val entity = ActivityEntity.create(
            title = title.ifBlank { "Untitled" },
            startedAt = started,
            endedAt = ended,
            category = category,
            tag = tag,
            notes = notes,
            color = color,
            isTimed = true
        )
        return dao.insert(entity)
    }

    suspend fun update(activity: ActivityEntity) = dao.update(activity)

    suspend fun delete(id: Long) = dao.deleteById(id)

    // ---------- Observation ----------

    fun observeRecent(limit: Int = 10): Flow<List<ActivityEntity>> = dao.observeRecent(limit)

    fun observeToday(): Flow<List<ActivityEntity>> {
        val range = DateUtils.todayRange()
        return dao.observeRange(range.startIso, range.endIso)
    }

    fun observeRange(range: IsoRange): Flow<List<ActivityEntity>> =
        dao.observeRange(range.startIso, range.endIso)

    // ---------- Aggregations ----------

    suspend fun totalInRange(range: IsoRange, category: String? = null, tag: String? = null): Long =
        dao.totalInRange(range.startIso, range.endIso, category, tag)

    suspend fun byCategory(range: IsoRange): List<CategoryTotal> =
        dao.byCategory(range.startIso, range.endIso)

    suspend fun byTag(range: IsoRange): List<LabelTotal> =
        dao.byTag(range.startIso, range.endIso)

    suspend fun dailyTotals(range: IsoRange): List<DayTotal> =
        dao.dailyTotals(range.startIso, range.endIso)

    suspend fun hourHistogram(range: IsoRange): List<HourTotal> =
        dao.hourHistogram(range.startIso, range.endIso)

    suspend fun dowHistogram(range: IsoRange): List<DowTotal> =
        dao.dowHistogram(range.startIso, range.endIso)

    suspend fun range(range: IsoRange): List<ActivityEntity> =
        dao.range(range.startIso, range.endIso)

    suspend fun all(): List<ActivityEntity> = dao.all()

    suspend fun count(): Int = dao.count()
}
