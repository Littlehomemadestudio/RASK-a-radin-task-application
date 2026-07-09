package com.rask.app.ui.home

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.speech.RecognizerIntent
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.rask.app.R
import com.rask.app.RaskApplication
import com.rask.app.data.db.entity.TemplateEntity
import com.rask.app.databinding.ActivityQuickLogBinding
import com.rask.app.service.TimerService
import com.rask.app.utils.DateUtils
import com.rask.app.utils.LocaleHelper
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import java.time.LocalDateTime

/**
 * Quick-log overlay.
 *
 * Two paths:
 *   1. Manual entry — title + HH:MM + category + notes → save.
 *   2. Start timer — title + category → [TimerService] starts.
 *
 * Voice input is wired to the platform speech recognizer; on devices without
 * it we show a friendly toast and stay editable.
 */
class QuickLogActivity : AppCompatActivity() {

    private lateinit var binding: ActivityQuickLogBinding
    private lateinit var templatesAdapter: TemplatesAdapter

    private val voiceLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val text = result.data
                ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull()
                .orEmpty()
            if (text.isNotBlank()) {
                binding.titleInput.setText(text)
            }
        }
    }

    override fun attachBaseContext(newBase: android.content.Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityQuickLogBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Tap outside the card → dismiss
        binding.root.setOnClickListener { finish() }
        binding.card.setOnClickListener { /* swallow */ }

        binding.btnClose.setOnClickListener { finish() }

        // Voice
        binding.btnVoice.setOnClickListener { startVoiceInput() }

        // Save
        binding.btnSave.setOnClickListener { saveManual() }

        // Start timer
        binding.btnStartTimer.setOnClickListener { startTimer() }

        // Categories dropdown
        lifecycleScope.launch {
            val app = application as RaskApplication
            app.categoryRepo.observeActive().collectLatest { cats ->
                val names = cats.map { it.name }
                val adapter = ArrayAdapter(
                    this@QuickLogActivity,
                    android.R.layout.simple_list_item_1,
                    names
                )
                binding.categoryInput.setAdapter(adapter)
                binding.categoryInput.threshold = 1
            }
        }

        // Templates
        templatesAdapter = TemplatesAdapter { template -> applyTemplate(template) }
        binding.templatesList.layoutManager =
            LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        binding.templatesList.adapter = templatesAdapter
        lifecycleScope.launch {
            val app = application as RaskApplication
            app.templateRepo.observeAll().collectLatest { ts ->
                templatesAdapter.submit(ts)
                binding.templatesLabel.visibility =
                    if (ts.isEmpty()) View.GONE else View.VISIBLE
            }
        }
    }

    private fun applyTemplate(t: TemplateEntity) {
        binding.titleInput.setText(t.name)
        if (t.defaultMillis > 0) {
            val (h, m) = DateUtils.millisToHhMm(t.defaultMillis)
            binding.hoursInput.setText(h.toString())
            binding.minutesInput.setText(m.toString())
        }
        if (!t.category.isNullOrBlank()) {
            binding.categoryInput.setText(t.category, false)
        }
    }

    private fun startVoiceInput() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, java.util.Locale.getDefault().toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_PROMPT, getString(R.string.quick_log_voice_hint))
        }
        try {
            voiceLauncher.launch(intent)
        } catch (_: Exception) {
            Toast.makeText(this, R.string.quick_log_voice_unavailable, Toast.LENGTH_SHORT).show()
        }
    }

    private fun saveManual() {
        val title = binding.titleInput.text?.toString().orEmpty().trim()
        val hours = binding.hoursInput.text?.toString()?.toIntOrNull() ?: 0
        val minutes = binding.minutesInput.text?.toString()?.toIntOrNull() ?: 0
        val durationMs = (hours * 3_600_000L) + (minutes * 60_000L)

        if (title.isBlank() || durationMs <= 0L) {
            Toast.makeText(this, R.string.quick_log_invalid, Toast.LENGTH_SHORT).show()
            return
        }

        val category = binding.categoryInput.text?.toString()?.ifBlank { null }
        val notes = binding.notesInput.text?.toString()?.ifBlank { null }

        val now = LocalDateTime.now()
        val start = now.minusMinutes((durationMs / 60000L).coerceAtLeast(0L))
            .minusSeconds((durationMs / 1000L) % 60)

        lifecycleScope.launch {
            val app = application as RaskApplication
            app.activityRepo.logManual(
                title = title,
                startedAt = start,
                endedAt = now,
                category = category,
                tag = null,
                notes = notes,
                color = null
            )
            app.goalRepo.recomputeAll()
            com.rask.app.widget.RaskWidgetProvider.updateAll(this@QuickLogActivity)
            Toast.makeText(this@QuickLogActivity, R.string.save, Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    private fun startTimer() {
        val title = binding.titleInput.text?.toString().orEmpty().trim()
        val category = binding.categoryInput.text?.toString()?.ifBlank { null }

        lifecycleScope.launch {
            val app = application as RaskApplication
            app.prefs.setTimerTitle(title)
            app.prefs.setTimerCategory(category)
            app.prefs.setTimerTag(null)
            app.prefs.setTimerAccumulatedMs(0L)
            app.prefs.setTimerStartedAt(DateUtils.nowUtcIso())
            app.prefs.setTimerPausedAt("")

            TimerService.start(this@QuickLogActivity)
            finish()
        }
    }
}
