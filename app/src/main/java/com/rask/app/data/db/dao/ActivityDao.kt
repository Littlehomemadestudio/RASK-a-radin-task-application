package com.rask.app.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.rask.app.data.db.entity.ActivityEntity
import kotlinx.coroutines.flow.Flow

/**
 * Activity DAO.
 *
 * All aggregations are pre-grouped at the SQL layer for speed — we never
 * pull the entire activities table into Kotlin.
 */
@Dao
interface ActivityDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(activity: ActivityEntity): Long

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(activities: List<ActivityEntity>): List<Long>

    @Update
    suspend fun update(activity: ActivityEntity)

    @Query("DELETE FROM activities WHERE id = :id")
    suspend fun deleteById(id: Long)

    @Query("DELETE FROM activities")
    suspend fun deleteAll()

    @Query("SELECT * FROM activities WHERE id = :id")
    suspend fun getById(id: Long): ActivityEntity?

    @Query("SELECT * FROM activities ORDER BY started_at DESC LIMIT :limit")
    fun observeRecent(limit: Int): Flow<List<ActivityEntity>>

    @Query("SELECT * FROM activities ORDER BY started_at DESC")
    fun observeAll(): Flow<List<ActivityEntity>>

    /**
     * Activities within an inclusive [startIso, endIso] ISO-8601 range.
     * Used for date-range aggregation.
     */
    @Query(
        """
        SELECT * FROM activities
        WHERE started_at >= :startIso AND started_at <= :endIso
        ORDER BY started_at DESC
        """
    )
    suspend fun range(startIso: String, endIso: String): List<ActivityEntity>

    @Query(
        """
        SELECT * FROM activities
        WHERE started_at >= :startIso AND started_at <= :endIso
        ORDER BY started_at DESC
        """
    )
    fun observeRange(startIso: String, endIso: String): Flow<List<ActivityEntity>>

    /**
     * Total duration in a range, optionally filtered by category and/or tag.
     * Returns 0 when no rows match.
     */
    @Query(
        """
        SELECT COALESCE(SUM(duration_millis), 0) FROM activities
        WHERE started_at >= :startIso AND started_at <= :endIso
          AND (:category IS NULL OR category = :category)
          AND (:tag IS NULL OR tag = :tag)
        """
    )
    suspend fun totalInRange(
        startIso: String,
        endIso: String,
        category: String?,
        tag: String?
    ): Long

    /**
     * Per-category sums in a range. Used for donut/bar charts.
     * Returns one row per category (or NULL category for untagged).
     */
    @Query(
        """
        SELECT
            COALESCE(category, '') AS label,
            SUM(duration_millis) AS totalMillis
        FROM activities
        WHERE started_at >= :startIso AND started_at <= :endIso
        GROUP BY category
        ORDER BY totalMillis DESC
        """
    )
    suspend fun byCategory(startIso: String, endIso: String): List<CategoryTotal>

    @Query(
        """
        SELECT
            COALESCE(tag, '') AS label,
            SUM(duration_millis) AS totalMillis
        FROM activities
        WHERE started_at >= :startIso AND started_at <= :endIso
          AND tag IS NOT NULL AND tag != ''
        GROUP BY tag
        ORDER BY totalMillis DESC
        """
    )
    suspend fun byTag(startIso: String, endIso: String): List<LabelTotal>

    /** Daily totals in a range. Used for heatmap + trend charts. */
    @Query(
        """
        SELECT
            substr(started_at, 1, 10) AS day,
            SUM(duration_millis) AS totalMillis
        FROM activities
        WHERE started_at >= :startIso AND started_at <= :endIso
        GROUP BY day
        ORDER BY day ASC
        """
    )
    suspend fun dailyTotals(startIso: String, endIso: String): List<DayTotal>

    /** Hour-of-day histogram (0..23). Used for "peak hour" insight. */
    @Query(
        """
        SELECT
            CAST(substr(started_at, 12, 2) AS INTEGER) AS hour,
            SUM(duration_millis) AS totalMillis
        FROM activities
        WHERE started_at >= :startIso AND started_at <= :endIso
        GROUP BY hour
        ORDER BY hour ASC
        """
    )
    suspend fun hourHistogram(startIso: String, endIso: String): List<HourTotal>

    /** Day-of-week histogram (1..7, Mon..Sun — ISO 8601). */
    @Query(
        """
        SELECT
            (CAST(substr(started_at, 9, 2) AS INTEGER) % 7) + 1 AS dow,
            SUM(duration_millis) AS totalMillis
        FROM activities
        WHERE started_at >= :startIso AND started_at <= :endIso
        GROUP BY dow
        ORDER BY dow ASC
        """
    )
    suspend fun dowHistogram(startIso: String, endIso: String): List<DowTotal>

    @Query("SELECT COUNT(*) FROM activities")
    suspend fun count(): Int

    @Query("SELECT * FROM activities")
    suspend fun all(): List<ActivityEntity>
}

// ---------- Aggregation result holders ----------

data class CategoryTotal(
    val label: String,
    val totalMillis: Long
)

data class LabelTotal(
    val label: String,
    val totalMillis: Long
)

data class DayTotal(
    val day: String,        // "2024-07-09"
    val totalMillis: Long
)

data class HourTotal(
    val hour: Int,
    val totalMillis: Long
)

data class DowTotal(
    val dow: Int,
    val totalMillis: Long
)
