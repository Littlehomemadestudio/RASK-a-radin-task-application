package com.rask.app.data.db.entity

import android.os.Parcelable
import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import kotlinx.parcelize.Parcelize

/**
 * Snapshot of the user's best streak per goal.
 *
 * Room tracks streaks by recomputing daily on app open (see [com.rask.app.data.repository.GoalRepository]).
 * This table is a fast-access cache of "best ever" + "current" streak counters.
 */
@Parcelize
@Entity(
    tableName = "streaks",
    indices = [Index(value = ["goal_id"], unique = true)]
)
data class StreakEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0L,

    /** FK to [GoalEntity.id]. */
    @ColumnInfo(name = "goal_id")
    val goalId: Long,

    /** Current streak (consecutive periods hitting the goal). */
    @ColumnInfo(name = "current")
    val current: Int = 0,

    /** Best ever streak. */
    @ColumnInfo(name = "best")
    val best: Int = 0,

    /** UTC ISO-8601 of the last period that hit the goal. */
    @ColumnInfo(name = "last_hit_at")
    val lastHitAt: String? = null,

    @ColumnInfo(name = "updated_at")
    val updatedAt: Long = System.currentTimeMillis()
) : Parcelable
