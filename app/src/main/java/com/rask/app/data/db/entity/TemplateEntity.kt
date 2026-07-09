package com.rask.app.data.db.entity

import android.os.Parcelable
import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import kotlinx.parcelize.Parcelize

/**
 * A recurring activity template. Stores title, default duration, category, tag,
 * so the user can one-tap log it. Displayed in the templates strip above quick-log.
 */
@Parcelize
@Entity(
    tableName = "templates",
    indices = [Index(value = ["sort_order"])]
)
data class TemplateEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0L,

    @ColumnInfo(name = "name")
    val name: String,

    /** Default duration in ms (0 means "no default"). */
    @ColumnInfo(name = "default_millis")
    val defaultMillis: Long = 0L,

    @ColumnInfo(name = "category")
    val category: String? = null,

    @ColumnInfo(name = "tag")
    val tag: String? = null,

    @ColumnInfo(name = "color")
    val color: String? = null,

    @ColumnInfo(name = "sort_order")
    val sortOrder: Int = 0,

    @ColumnInfo(name = "created_at")
    val createdAt: Long = System.currentTimeMillis()
) : Parcelable
