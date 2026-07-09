package com.rask.app.data.db.entity

import android.os.Parcelable
import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import kotlinx.parcelize.Parcelize
import java.time.LocalDateTime

/**
 * A single timed activity entry.
 *
 * - [startedAt] and [endedAt] are stored as ISO-8601 strings (UTC) so we can
 *   round-trip them through encrypted backups without tz data loss.
 * - [durationMillis] is denormalised for fast aggregation queries.
 * - [category] and [tag] are denormalised strings (not FKs) to allow
 *   category renaming without cascade cost. They are indexed for filter speed.
 */
@Parcelize
@Entity(
    tableName = "activities",
    indices = [
        Index(value = ["started_at"]),
        Index(value = ["category"]),
        Index(value = ["tag"]),
        Index(value = ["ended_at"])
    ]
)
data class ActivityEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0L,

    /** Free-form title, e.g. "Deep work — chapter 4". */
    @ColumnInfo(name = "title")
    val title: String,

    /** UTC ISO-8601 timestamp of when the activity began. */
    @ColumnInfo(name = "started_at")
    val startedAt: String,

    /** UTC ISO-8601 timestamp of when the activity ended. */
    @ColumnInfo(name = "ended_at")
    val endedAt: String,

    /** Pre-computed elapsed time in ms. Stored for fast aggregation. */
    @ColumnInfo(name = "duration_millis")
    val durationMillis: Long,

    /** Optional category name (denormalised; matches [CategoryEntity.name]). */
    @ColumnInfo(name = "category")
    val category: String? = null,

    /** Optional free-form tag. */
    @ColumnInfo(name = "tag")
    val tag: String? = null,

    /** Optional note body. */
    @ColumnInfo(name = "notes")
    val notes: String? = null,

    /** Optional color label hex (e.g. "#D4AF37") — overrides category color when set. */
    @ColumnInfo(name = "color")
    val color: String? = null,

    /** True if the entry was produced by the stopwatch; false if entered manually. */
    @ColumnInfo(name = "is_timed")
    val isTimed: Boolean = false,

    /** Creation timestamp, used for ordering. */
    @ColumnInfo(name = "created_at")
    val createdAt: Long = System.currentTimeMillis()
) : Parcelable {
    companion object {
        /** Convenience factory used by manual log + stopwatch save. */
        fun create(
            title: String,
            startedAt: LocalDateTime,
            endedAt: LocalDateTime,
            category: String? = null,
            tag: String? = null,
            notes: String? = null,
            color: String? = null,
            isTimed: Boolean
        ): ActivityEntity {
            return ActivityEntity(
                title = title,
                startedAt = startedAt.toString(),
                endedAt = endedAt.toString(),
                durationMillis = java.time.Duration.between(startedAt, endedAt).toMillis(),
                category = category?.ifBlank { null },
                tag = tag?.ifBlank { null },
                notes = notes?.ifBlank { null },
                color = color?.ifBlank { null },
                isTimed = isTimed
            )
        }
    }
}
