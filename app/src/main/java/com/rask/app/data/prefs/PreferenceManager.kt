package com.rask.app.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "rask_prefs")

/**
 * DataStore-backed preferences. Single source of truth for UI flags that
 * don't belong in the Room database (theme, language, lock, reminder time).
 *
 * All values are exposed as [Flow]s so the UI can react in real time.
 */
class PreferenceManager(private val context: Context) {

    // ---------- Theme ----------
    val amoledMode: Flow<Boolean> = context.dataStore.data.map { it[AMOLED] ?: false }
    suspend fun setAmoled(enabled: Boolean) {
        context.dataStore.edit { it[AMOLED] = enabled }
    }

    // ---------- Language ----------
    /** "system", "en", "fa" */
    val language: Flow<String> = context.dataStore.data.map { it[LANGUAGE] ?: "system" }
    suspend fun setLanguage(code: String) {
        context.dataStore.edit { it[LANGUAGE] = code }
    }

    // ---------- App lock ----------
    val appLockEnabled: Flow<Boolean> = context.dataStore.data.map { it[APP_LOCK_ENABLED] ?: false }
    suspend fun setAppLockEnabled(enabled: Boolean) {
        context.dataStore.edit { it[APP_LOCK_ENABLED] = enabled }
    }

    val biometricsEnabled: Flow<Boolean> = context.dataStore.data.map { it[BIOMETRICS] ?: false }
    suspend fun setBiometricsEnabled(enabled: Boolean) {
        context.dataStore.edit { it[BIOMETRICS] = enabled }
    }

    /** SHA-256 hash of the PIN, base64. Empty when no PIN is set. */
    val pinHash: Flow<String> = context.dataStore.data.map { it[PIN_HASH] ?: "" }
    suspend fun setPinHash(hash: String) {
        context.dataStore.edit { it[PIN_HASH] = hash }
    }

    // ---------- Reminders ----------
    val remindersEnabled: Flow<Boolean> = context.dataStore.data.map { it[REMINDERS_ENABLED] ?: false }
    suspend fun setRemindersEnabled(enabled: Boolean) {
        context.dataStore.edit { it[REMINDERS_ENABLED] = enabled }
    }

    /** Hour of day 0..23 */
    val reminderHour: Flow<Int> = context.dataStore.data.map { it[REMINDER_HOUR] ?: 21 }
    suspend fun setReminderHour(hour: Int) {
        context.dataStore.edit { it[REMINDER_HOUR] = hour.coerceIn(0, 23) }
    }

    /** Minute 0..59 */
    val reminderMinute: Flow<Int> = context.dataStore.data.map { it[REMINDER_MINUTE] ?: 0 }
    suspend fun setReminderMinute(min: Int) {
        context.dataStore.edit { it[REMINDER_MINUTE] = min.coerceIn(0, 59) }
    }

    // ---------- Onboarding ----------
    val onboardingCompleted: Flow<Boolean> = context.dataStore.data.map { it[ONBOARDING_DONE] ?: false }
    suspend fun setOnboardingCompleted(done: Boolean) {
        context.dataStore.edit { it[ONBOARDING_DONE] = done }
    }

    // ---------- Timer state (persisted across process death) ----------
    /** ISO timestamp of when the current timer started, or "" if no timer. */
    val timerStartedAt: Flow<String> = context.dataStore.data.map { it[TIMER_STARTED_AT] ?: "" }
    suspend fun setTimerStartedAt(iso: String) {
        context.dataStore.edit { it[TIMER_STARTED_AT] = iso }
    }

    /** ISO timestamp of when the timer was paused, or "". */
    val timerPausedAt: Flow<String> = context.dataStore.data.map { it[TIMER_PAUSED_AT] ?: "" }
    suspend fun setTimerPausedAt(iso: String) {
        context.dataStore.edit { it[TIMER_PAUSED_AT] = iso }
    }

    /** Accumulated ms when paused (in case of multiple pause/resume cycles). */
    val timerAccumulatedMs: Flow<Long> = context.dataStore.data.map { it[TIMER_ACCUMULATED] ?: 0L }
    suspend fun setTimerAccumulatedMs(ms: Long) {
        context.dataStore.edit { it[TIMER_ACCUMULATED] = ms }
    }

    /** Activity title the user typed before pressing "Start timer". */
    val timerTitle: Flow<String> = context.dataStore.data.map { it[TIMER_TITLE] ?: "" }
    suspend fun setTimerTitle(title: String) {
        context.dataStore.edit { it[TIMER_TITLE] = title }
    }

    val timerCategory: Flow<String?> = context.dataStore.data.map { it[TIMER_CATEGORY] }
    suspend fun setTimerCategory(category: String?) {
        context.dataStore.edit { it[TIMER_CATEGORY] = category }
    }

    val timerTag: Flow<String?> = context.dataStore.data.map { it[TIMER_TAG] }
    suspend fun setTimerTag(tag: String?) {
        context.dataStore.edit { it[TIMER_TAG] = tag }
    }

    suspend fun clearTimer() {
        context.dataStore.edit {
            it[TIMER_STARTED_AT] = ""
            it[TIMER_PAUSED_AT] = ""
            it[TIMER_ACCUMULATED] = 0L
            it[TIMER_TITLE] = ""
            it[TIMER_CATEGORY] = null
            it[TIMER_TAG] = null
        }
    }

    companion object {
        private val AMOLED = booleanPreferencesKey("amoled_mode")
        private val LANGUAGE = stringPreferencesKey("language_code")
        private val APP_LOCK_ENABLED = booleanPreferencesKey("app_lock_enabled")
        private val BIOMETRICS = booleanPreferencesKey("biometrics_enabled")
        private val PIN_HASH = stringPreferencesKey("pin_hash")
        private val REMINDERS_ENABLED = booleanPreferencesKey("reminders_enabled")
        private val REMINDER_HOUR = intPreferencesKey("reminder_hour")
        private val REMINDER_MINUTE = intPreferencesKey("reminder_minute")
        private val ONBOARDING_DONE = booleanPreferencesKey("onboarding_done")

        private val TIMER_STARTED_AT = stringPreferencesKey("timer_started_at")
        private val TIMER_PAUSED_AT = stringPreferencesKey("timer_paused_at")
        private val TIMER_ACCUMULATED = longPreferencesKey("timer_accumulated_ms")
        private val TIMER_TITLE = stringPreferencesKey("timer_title")
        private val TIMER_CATEGORY = stringPreferencesKey("timer_category")
        private val TIMER_TAG = stringPreferencesKey("timer_tag")
    }
}
