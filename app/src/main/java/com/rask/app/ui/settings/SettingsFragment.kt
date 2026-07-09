package com.rask.app.ui.settings

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.snackbar.Snackbar
import com.rask.app.R
import com.rask.app.RaskApplication
import com.rask.app.databinding.FragmentSettingsBinding
import com.rask.app.utils.LocaleHelper
import kotlinx.coroutines.launch
import java.security.MessageDigest

class SettingsFragment : Fragment() {

    private var _binding: FragmentSettingsBinding? = null
    private val binding get() = _binding!!
    private val vm: SettingsViewModel by viewModels()

    private val createBackupLauncher = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/octet-stream")
    ) { uri: Uri? ->
        uri ?: return@registerForActivityResult
        promptForPassword(promptRes = R.string.backup_password_title,
            hintRes = R.string.backup_password_hint) { password ->
            lifecycleScope.launch {
                val app = requireActivity().application as RaskApplication
                val out = requireContext().contentResolver.openOutputStream(uri) ?: return@launch
                out.use {
                    app.backupManager.export(it, password.toCharArray())
                }
                Snackbar.make(binding.root, R.string.backup_done, Snackbar.LENGTH_LONG).show()
            }
        }
    }

    private val openBackupLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        uri ?: return@registerForActivityResult
        promptForPassword(promptRes = R.string.backup_password_title,
            hintRes = R.string.backup_restore_password_hint) { password ->
            lifecycleScope.launch {
                val app = requireActivity().application as RaskApplication
                val input = requireContext().contentResolver.openInputStream(uri) ?: return@launch
                val ok = input.use { app.backupManager.import(it, password.toCharArray()) }
                Snackbar.make(
                    binding.root,
                    if (ok) R.string.backup_restore_done else R.string.backup_restore_failed,
                    Snackbar.LENGTH_LONG
                ).show()
            }
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentSettingsBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Language dropdown
        val langs = listOf(
            Triple("system", getString(R.string.settings_language_system), true),
            Triple("en", getString(R.string.settings_language_en), false),
            Triple("fa", getString(R.string.settings_language_fa), false)
        )
        val langLabels = langs.map { it.second }
        val langAdapter = ArrayAdapter(
            requireContext(),
            android.R.layout.simple_list_item_1,
            langLabels
        )
        binding.languageInput.setAdapter(langAdapter)
        binding.languageInput.threshold = 1

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { vm.amoled.observe { binding.swAmoled.isChecked = it } }
                launch { vm.language.observe { code ->
                    val idx = langs.indexOfFirst { it.first == code }
                    if (idx >= 0) binding.languageInput.setText(langLabels[idx], false)
                }}
                launch { vm.appLockEnabled.observe { v ->
                    binding.swAppLock.isChecked = v
                    binding.appLockSummary.setText(
                        if (v) R.string.settings_app_lock_summary_on
                        else R.string.settings_app_lock_summary_off
                    )
                }}
                launch { vm.biometrics.observe { binding.swBiometrics.isChecked = it } }
                launch { vm.remindersEnabled.observe { binding.swReminders.isChecked = it } }
                launch { vm.hasPin.observe { /* reflect via appLockSummary */ } }
            }
        }

        // Toggle handlers
        binding.swAmoled.setOnCheckedChangeListener { _, checked -> vm.setAmoled(checked) }
        binding.languageInput.setOnItemClickListener { _, _, position, _ ->
            val code = langs[position].first
            vm.setLanguage(code)
            LocaleHelper.apply(code)
            // Recreate the activity to apply
            requireActivity().recreate()
        }
        binding.swAppLock.setOnCheckedChangeListener { _, checked ->
            if (checked && !vm.hasPin.value!!) {
                // Need to set a PIN first
                binding.swAppLock.isChecked = false
                promptForPinSetup()
            } else {
                vm.setAppLock(checked)
            }
        }
        binding.swBiometrics.setOnCheckedChangeListener { _, checked -> vm.setBiometrics(checked) }
        binding.swReminders.setOnCheckedChangeListener { _, checked -> vm.setReminders(checked) }

        // Data
        binding.btnBackup.setOnClickListener {
            createBackupLauncher.launch("rask-backup-${System.currentTimeMillis()}.rask")
        }
        binding.btnRestore.setOnClickListener {
            openBackupLauncher.launch(arrayOf("application/octet-stream", "*/*"))
        }
        binding.btnExportCsv.setOnClickListener {
            viewLifecycleOwner.lifecycleScope.launch {
                val path = com.rask.app.ui.stats.StatsExporter.exportCsv(requireContext())
                val msg = if (path != null)
                    getString(R.string.stats_export_success, path)
                else
                    getString(R.string.stats_export_failed)
                Snackbar.make(binding.root, msg, Snackbar.LENGTH_LONG).show()
            }
        }
        binding.btnClear.setOnClickListener {
            MaterialAlertDialogBuilder(requireContext())
                .setTitle(R.string.settings_clear)
                .setMessage(R.string.settings_clear_summary)
                .setNegativeButton(R.string.cancel, null)
                .setPositiveButton(R.string.delete) { _, _ ->
                    viewLifecycleOwner.lifecycleScope.launch {
                        com.rask.app.data.db.RaskDatabase.clear(requireContext())
                        Snackbar.make(binding.root, R.string.close, Snackbar.LENGTH_SHORT).show()
                    }
                }
                .show()
        }

        // Version label
        try {
            val pkg = requireContext().packageManager.getPackageInfo(requireContext().packageName, 0)
            binding.versionLabel.text = "${getString(R.string.settings_version)} ${pkg.versionName}"
        } catch (_: Throwable) {
            binding.versionLabel.text = "${getString(R.string.settings_version)} —"
        }
    }

    private fun promptForPassword(promptRes: Int, hintRes: Int, onResult: (String) -> Unit) {
        val input = android.widget.EditText(requireContext()).apply {
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            hint = getString(hintRes)
            setTextColor(android.graphics.Color.WHITE)
        }
        MaterialAlertDialogBuilder(requireContext())
            .setTitle(promptRes)
            .setView(input)
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.confirm) { _, _ ->
                val pwd = input.text.toString()
                if (pwd.length < 4) {
                    Toast.makeText(requireContext(), R.string.backup_failed, Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                onResult(pwd)
            }
            .show()
    }

    private fun promptForPinSetup() {
        val view = LayoutInflater.from(requireContext())
            .inflate(R.layout.dialog_pin_setup, null, false)
        val pin1 = view.findViewById<android.widget.EditText>(R.id.pinInput1)
        val pin2 = view.findViewById<android.widget.EditText>(R.id.pinInput2)

        MaterialAlertDialogBuilder(requireContext())
            .setTitle(R.string.lock_setup_pin)
            .setView(view)
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.save) { _, _ ->
                val a = pin1.text.toString()
                val b = pin2.text.toString()
                if (a.length != 4 || a != b) {
                    Toast.makeText(requireContext(), R.string.lock_pin_mismatch, Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                val hash = sha256(a)
                vm.setPinHash(hash)
                vm.setAppLock(true)
            }
            .show()
    }

    private fun sha256(s: String): String {
        val md = MessageDigest.getInstance("SHA-256")
        val bytes = md.digest(s.toByteArray(Charsets.UTF_8))
        return android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
