package com.rask.app.utils

import java.time.DayOfWeek
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.YearMonth
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.time.temporal.TemporalAdjusters
import java.util.Locale

/**
 * Centralised date utilities — every timestamp in the app should pass through
 * here so we have a single source of truth for parsing/formatting/tz math.
 *
 * Storage convention: ISO-8601 strings in UTC (e.g. "2024-07-09T13:45:00Z").
 * Display convention: local-zone, locale-aware.
 */
object DateUtils {

    private val isoUtc: DateTimeFormatter =
        DateTimeFormatter.ISO_OFFSET_DATE_TIME

    /** "Now" in the user's local timezone, suitable for storage as UTC. */
    fun nowUtcIso(): String =
        ZonedDateTime.now(ZoneId.systemDefault())
            .toOffsetDateTime()
            .format(isoUtc)

    fun toUtcIso(local: LocalDateTime): String =
        local.atZone(ZoneId.systemDefault()).toOffsetDateTime().format(isoUtc)

    fun fromUtcIso(iso: String): LocalDateTime =
        ZonedDateTime.parse(iso, isoUtc)
            .withZoneSameInstant(ZoneId.systemDefault())
            .toLocalDateTime()

    // ---------- Ranges ----------

    data class IsoRange(val startIso: String, val endIso: String)

    fun todayRange(): IsoRange {
        val start = LocalDate.now().atStartOfDay()
        val end = LocalDate.now().atTime(LocalTime.MAX)
        return IsoRange(toUtcIso(start), toUtcIso(end))
    }

    fun yesterdayRange(): IsoRange {
        val yesterday = LocalDate.now().minusDays(1)
        return IsoRange(
            toUtcIso(yesterday.atStartOfDay()),
            toUtcIso(yesterday.atTime(LocalTime.MAX))
        )
    }

    fun thisWeekRange(): IsoRange {
        // Monday-start weeks (ISO-8601)
        val today = LocalDate.now()
        val monday = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        val sunday = monday.plusDays(6)
        return IsoRange(
            toUtcIso(monday.atStartOfDay()),
            toUtcIso(sunday.atTime(LocalTime.MAX))
        )
    }

    fun thisMonthRange(): IsoRange {
        val today = LocalDate.now()
        val ym = YearMonth.of(today.year, today.month)
        return IsoRange(
            toUtcIso(ym.atDay(1).atStartOfDay()),
            toUtcIso(ym.atEndOfMonth().atTime(LocalTime.MAX))
        )
    }

    fun last30DaysRange(): IsoRange {
        val today = LocalDate.now()
        val start = today.minusDays(29)
        return IsoRange(
            toUtcIso(start.atStartOfDay()),
            toUtcIso(today.atTime(LocalTime.MAX))
        )
    }

    fun thisYearRange(): IsoRange {
        val year = LocalDate.now().year
        return IsoRange(
            toUtcIso(LocalDate.of(year, 1, 1).atStartOfDay()),
            toUtcIso(LocalDate.of(year, 12, 31).atTime(LocalTime.MAX))
        )
    }

    fun allTimeRange(): IsoRange {
        // A very-wide range — covers all practical timestamps
        return IsoRange(
            toUtcIso(LocalDateTime.of(1970, 1, 1, 0, 0)),
            toUtcIso(LocalDateTime.of(2999, 12, 31, 23, 59))
        )
    }

    fun customRange(start: LocalDate, end: LocalDate): IsoRange =
        IsoRange(
            toUtcIso(start.atStartOfDay()),
            toUtcIso(end.atTime(LocalTime.MAX))
        )

    // ---------- Display ----------

    /** "9 Jul" or "۹ تیر" depending on locale. */
    fun shortDate(local: LocalDateTime, locale: Locale = Locale.getDefault()): String {
        val fmt = DateTimeFormatter.ofPattern("d MMM", locale)
        return local.format(fmt)
    }

    /** "9 Jul 2024" or local equivalent. */
    fun mediumDate(local: LocalDateTime, locale: Locale = Locale.getDefault()): String {
        val fmt = DateTimeFormatter.ofPattern("d MMM yyyy", locale)
        return local.format(fmt)
    }

    /** "13:45" — 24h, locale-aware. */
    fun shortTime(local: LocalDateTime, locale: Locale = Locale.getDefault()): String {
        val fmt = DateTimeFormatter.ofPattern("HH:mm", locale)
        return local.format(fmt)
    }

    fun dayOfWeekLabel(dow: DayOfWeek, locale: Locale = Locale.getDefault()): String =
        dow.getDisplayName(TextStyle.SHORT, locale)

    /** "2024-07-09" — bucket key used by heatmap. */
    fun dayBucket(local: LocalDateTime): String {
        val fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd")
        return local.toLocalDate().format(fmt)
    }

    fun parseDayBucket(bucket: String): LocalDate =
        LocalDate.parse(bucket, DateTimeFormatter.ofPattern("yyyy-MM-dd"))

    // ---------- Durations ----------

    fun millisToHhMmSs(millis: Long): String {
        val totalSeconds = millis / 1000
        val h = totalSeconds / 3600
        val m = (totalSeconds % 3600) / 60
        val s = totalSeconds % 60
        return String.format(Locale.US, "%02d:%02d:%02d", h, m, s)
    }

    fun millisToHhMm(millis: Long): Pair<Long, Long> {
        val totalMinutes = millis / 60000
        val h = totalMinutes / 60
        val m = totalMinutes % 60
        return h to m
    }

    fun durationLabel(millis: Long, locale: Locale = Locale.getDefault()): String {
        val (h, m) = millisToHhMm(millis)
        return when {
            h == 0L && m == 0L -> "0m"
            h == 0L -> "${m}m"
            m == 0L -> "${h}h"
            else -> "${h}h ${m}m"
        }
    }

    fun between(startIso: String, endIso: String): Long =
        Duration.between(fromUtcIso(startIso), fromUtcIso(endIso)).toMillis()
}
