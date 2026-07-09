package com.rask.app.ui.stats

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.viewModelScope
import com.rask.app.RaskApplication
import com.rask.app.data.db.dao.CategoryTotal
import com.rask.app.data.db.dao.DayTotal
import com.rask.app.data.db.dao.DowTotal
import com.rask.app.data.db.dao.HourTotal
import com.rask.app.data.db.dao.LabelTotal
import com.rask.app.utils.DateUtils
import kotlinx.coroutines.launch
import java.time.LocalDate

/**
 * Stats screen view model.
 *
 * Owns:
 *   - The selected date range (preset or custom)
 *   - Optional category + tag filters
 *   - Aggregated totals, charts, heatmap, trends
 */
class StatsViewModel(app: Application) : AndroidViewModel(app) {

    private val raskApp = app as RaskApplication

    enum class RangePreset(val labelRes: Int) {
        TODAY(com.rask.app.R.string.stats_today),
        YESTERDAY(com.rask.app.R.string.stats_yesterday),
        THIS_WEEK(com.rask.app.R.string.stats_this_week),
        THIS_MONTH(com.rask.app.R.string.stats_this_month),
        LAST_30(com.rask.app.R.string.stats_last_30),
        THIS_YEAR(com.rask.app.R.string.stats_this_year),
        ALL_TIME(com.rask.app.R.string.stats_all_time)
    }

    private val _preset = MutableLiveData(RangePreset.THIS_WEEK)
    val preset: LiveData<RangePreset> = _preset

    private val _total = MutableLiveData(0L)
    val total: LiveData<Long> = _total

    private val _categories = MutableLiveData<List<CategoryTotal>>(emptyList())
    val categories: LiveData<List<CategoryTotal>> = _categories

    private val _tags = MutableLiveData<List<LabelTotal>>(emptyList())
    val tags: LiveData<List<LabelTotal>> = _tags

    private val _daily = MutableLiveData<List<DayTotal>>(emptyList())
    val daily: LiveData<List<DayTotal>> = _daily

    private val _dow = MutableLiveData<List<DowTotal>>(emptyList())
    val dow: LiveData<List<DowTotal>> = _dow

    private val _hourly = MutableLiveData<List<HourTotal>>(emptyList())
    val hourly: LiveData<List<HourTotal>> = _hourly

    private val _bestDay = MutableLiveData<DayTotal?>(null)
    val bestDay: LiveData<DayTotal?> = _bestDay

    private val _peakHour = MutableLiveData<HourTotal?>(null)
    val peakHour: LiveData<HourTotal?> = _peakHour

    private val _weeklyAvg = MutableLiveData(0L)
    val weeklyAvg: LiveData<Long> = _weeklyAvg

    init { refresh() }

    fun setPreset(p: RangePreset) {
        _preset.value = p
        refresh()
    }

    fun setCustom(start: LocalDate, end: LocalDate) {
        // Custom range uses LAST_30 enum slot as a placeholder; we override the range
        // by storing the start/end in private vars and recomputing.
        customStart = start
        customEnd = end
        isCustom = true
        _preset.value = RangePreset.LAST_30 // will be overridden in rangeFor
        refresh()
    }

    private var customStart: LocalDate? = null
    private var customEnd: LocalDate? = null
    private var isCustom: Boolean = false

    fun currentRange(): DateUtils.IsoRange {
        val preset = _preset.value ?: RangePreset.THIS_WEEK
        if (isCustom && customStart != null && customEnd != null) {
            return DateUtils.customRange(customStart!!, customEnd!!)
        }
        return when (preset) {
            RangePreset.TODAY -> DateUtils.todayRange()
            RangePreset.YESTERDAY -> DateUtils.yesterdayRange()
            RangePreset.THIS_WEEK -> DateUtils.thisWeekRange()
            RangePreset.THIS_MONTH -> DateUtils.thisMonthRange()
            RangePreset.LAST_30 -> DateUtils.last30DaysRange()
            RangePreset.THIS_YEAR -> DateUtils.thisYearRange()
            RangePreset.ALL_TIME -> DateUtils.allTimeRange()
        }
    }

    private fun refresh() {
        viewModelScope.launch {
            val range = currentRange()
            _total.value = raskApp.activityRepo.totalInRange(range)
            _categories.value = raskApp.activityRepo.byCategory(range)
            _tags.value = raskApp.activityRepo.byTag(range)
            _daily.value = raskApp.activityRepo.dailyTotals(range)
            _dow.value = raskApp.activityRepo.dowHistogram(range)
            _hourly.value = raskApp.activityRepo.hourHistogram(range)

            _bestDay.value = _daily.value?.maxByOrNull { it.totalMillis }
            _peakHour.value = _hourly.value?.maxByOrNull { it.totalMillis }

            // Weekly average = (total / span days) * 7
            val days = daysInPreset().coerceAtLeast(1)
            _weeklyAvg.value = (_total.value ?: 0L) / days * 7L
        }
    }

    private fun daysInPreset(): Int {
        return when (_preset.value) {
            RangePreset.TODAY -> 1
            RangePreset.YESTERDAY -> 1
            RangePreset.THIS_WEEK -> 7
            RangePreset.THIS_MONTH -> 30
            RangePreset.LAST_30 -> 30
            RangePreset.THIS_YEAR -> 365
            RangePreset.ALL_TIME -> 365
            null -> 7
        }
    }
}
