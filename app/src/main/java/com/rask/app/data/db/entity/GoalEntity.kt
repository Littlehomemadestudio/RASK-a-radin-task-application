package com.rask.app.data.db.entity

import android.os.Parcelable
import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import kotlinx.parcelize.Parcelize

/**
 * A time-based goal. Scope is daily / weekly / monthly.
 *
 * - [targetMillis] is the per-period target.
 * - [categoryId] is null for an "overall" goal, otherwise a per-category goal.
 * - [active] toggles whether the goal participates in progress + streaks.
 */
@Parcelize
@Entity(
    tableName = "goals",
    indices = [
        Index(value = ["scope"]),
        Index(value = ["category_id"])
    ]
)
data class GoalEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0L,

    /** "DAILY", "WEEKLY", "MONTHLY" — see [GoalScope]. */
    @ColumnInfo(name = "scope")
    val scope: String,

    /** Target duration in ms for the period. */
    @ColumnInfo(name = "target_millis")
    val targetMillis: Long,

    /** Optional — when null, this is an overall goal. */
    @ColumnInfo(name = "category_id")
    val categoryId: Long? = null,

    /** Display name for the goal (auto-derived if null). */
    @ColumnInfo(name = "name")
    val name: String? = null,

    @ColumnInfo(name = "active")
    val active: Boolean = true,

    @ColumnInfo(name = "created_at")
    val createdAt: Long = System.currentTimeMillis()
) : Parcelable {
    companion object {
        const val SCOPE_DAILY = "DAILY"
        const val SCOPE_WEEKLY = "WEEKLY"
        const val SCOPE_MONTHLY = "MONTHLY"
    }
}
