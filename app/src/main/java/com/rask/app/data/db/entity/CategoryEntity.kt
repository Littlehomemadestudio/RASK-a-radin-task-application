package com.rask.app.data.db.entity

import android.os.Parcelable
import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import kotlinx.parcelize.Parcelize

/**
 * A user-defined category with a color label.
 *
 * Categories are soft-deletable (so historic activities keep their names)
 * but we don't actually delete them — we just hide them from the picker
 * when [archived] is true.
 */
@Parcelize
@Entity(
    tableName = "categories",
    indices = [Index(value = ["name"], unique = true)]
)
data class CategoryEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0L,

    @ColumnInfo(name = "name")
    val name: String,

    /** Hex color, e.g. "#D4AF37". Defaults to brand gold. */
    @ColumnInfo(name = "color")
    val color: String = "#D4AF37",

    /** Display order — lower sorts first. */
    @ColumnInfo(name = "sort_order")
    val sortOrder: Int = 0,

    @ColumnInfo(name = "archived")
    val archived: Boolean = false,

    @ColumnInfo(name = "created_at")
    val createdAt: Long = System.currentTimeMillis()
) : Parcelable
