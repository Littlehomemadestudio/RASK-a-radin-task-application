package com.rask.app.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.viewModelScope
import com.rask.app.RaskApplication
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class SettingsViewModel(app: Application) : AndroidViewModel(app) {

    private val raskApp = app as RaskApplication

    private val _amoled = MutableLiveData(false)
    val amoled: LiveData<Boolean> = _amoled

    private val _language = MutableLiveData("system")
    val language: LiveData<String> = _language

    private val _appLockEnabled = MutableLiveData(false)
    val appLockEnabled: LiveData<Boolean> = _appLockEnabled

    private val _biometrics = MutableLiveData(false)
    val biometrics: LiveData<Boolean> = _biometrics

    private val _hasPin = MutableLiveData(false)
    val hasPin: LiveData<Boolean> = _hasPin

    private val _remindersEnabled = MutableLiveData(false)
    val remindersEnabled: LiveData<Boolean> = _remindersEnabled

    private val _reminderHour = MutableLiveData(21)
    val reminderHour: LiveData<Int> = _reminderHour

    private val _reminderMinute = MutableLiveData(0)
    val reminderMinute: LiveData<Int> = _reminderMinute

    init {
        viewModelScope.launch {
            raskApp.prefs.amoledMode.collectLatest { _amoled.value = it }
        }
        viewModelScope.launch {
            raskApp.prefs.language.collectLatest { _language.value = it }
        }
        viewModelScope.launch {
            raskApp.prefs.appLockEnabled.collectLatest { _appLockEnabled.value = it }
        }
        viewModelScope.launch {
            raskApp.prefs.biometricsEnabled.collectLatest { _biometrics.value = it }
        }
        viewModelScope.launch {
            raskApp.prefs.pinHash.collectLatest { _hasPin.value = it.isNotBlank() }
        }
        viewModelScope.launch {
            raskApp.prefs.remindersEnabled.collectLatest { _remindersEnabled.value = it }
        }
        viewModelScope.launch {
            raskApp.prefs.reminderHour.collectLatest { _reminderHour.value = it }
        }
        viewModelScope.launch {
            raskApp.prefs.reminderMinute.collectLatest { _reminderMinute.value = it }
        }
    }

    fun setAmoled(v: Boolean) = viewModelScope.launch { raskApp.prefs.setAmoled(v) }
    fun setLanguage(code: String) = viewModelScope.launch { raskApp.prefs.setLanguage(code) }
    fun setAppLock(v: Boolean) = viewModelScope.launch { raskApp.prefs.setAppLockEnabled(v) }
    fun setBiometrics(v: Boolean) = viewModelScope.launch { raskApp.prefs.setBiometricsEnabled(v) }
    fun setPinHash(hash: String) = viewModelScope.launch { raskApp.prefs.setPinHash(hash) }
    fun setReminders(v: Boolean) = viewModelScope.launch {
        raskApp.prefs.setRemindersEnabled(v)
        com.rask.app.work.ReminderScheduler.scheduleIfEnabled(getApplication())
    }
    fun setReminderTime(h: Int, m: Int) = viewModelScope.launch {
        raskApp.prefs.setReminderHour(h)
        raskApp.prefs.setReminderMinute(m)
        com.rask.app.work.ReminderScheduler.scheduleIfEnabled(getApplication())
    }
}
