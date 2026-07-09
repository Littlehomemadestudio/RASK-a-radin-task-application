package com.rask.app.data.db.converters

import androidx.room.TypeConverter

/**
 * Minimal TypeConverters — most fields are stored as primitives or strings,
 * so we only need a couple of helpers for safety.
 */
class Converters {

    @TypeConverter
    fun fromBoolean(value: Boolean): Int = if (value) 1 else 0

    @TypeConverter
    fun toBoolean(value: Int): Boolean = value != 0

    @TypeConverter
    fun fromLongList(list: List<Long>?): String =
        list?.joinToString(",") ?: ""

    @TypeConverter
    fun toLongList(value: String?): List<Long> =
        if (value.isNullOrBlank()) emptyList()
        else value.split(",").mapNotNull { it.toLongOrNull() }
}
