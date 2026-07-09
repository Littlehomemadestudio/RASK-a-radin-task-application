package com.rask.app.ui.settings

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.rask.app.R
import com.rask.app.RaskApplication
import com.rask.app.databinding.ActivityLockBinding
import com.rask.app.utils.LocaleHelper
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.security.MessageDigest

/**
 * App-lock gate.
 *
 * Shown when the user has enabled app-lock. Offers two paths:
 *   1. Biometrics (if available + enabled)
 *   2. PIN
 *
 * On success: finishes with RESULT_OK → MainActivity opens.
 * On cancel / back-press: finishes with RESULT_CANCELED → app exits.
 */
class LockActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLockBinding

    override fun attachBaseContext(newBase: android.content.Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLockBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Disable back-press to bypass lock
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                finishAffinity()
            }
        })

        binding.pinInput.requestFocus()

        binding.btnConfirm.setOnClickListener { tryPin() }
        binding.btnBiometrics.setOnClickListener { tryBiometrics() }

        lifecycleScope.launch {
            val app = application as RaskApplication
            val biometricsEnabled = app.prefs.biometricsEnabled.first()
            val biometricsAvailable = BiometricManager.from(this@LockActivity)
                .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK) ==
                BiometricManager.BIOMETRIC_SUCCESS

            binding.btnBiometrics.visibility =
                if (biometricsEnabled && biometricsAvailable) View.VISIBLE
                else View.GONE

            // Auto-prompt biometrics on entry if available
            if (biometricsEnabled && biometricsAvailable) {
                binding.root.post { tryBiometrics() }
            }
        }
    }

    private fun tryPin() {
        val entered = binding.pinInput.text?.toString().orEmpty()
        lifecycleScope.launch {
            val app = application as RaskApplication
            val storedHash = app.prefs.pinHash.first()
            val enteredHash = sha256(entered)
            if (enteredHash == storedHash) {
                setResult(RESULT_OK)
                finish()
            } else {
                Toast.makeText(this@LockActivity, R.string.lock_wrong_pin, Toast.LENGTH_SHORT).show()
                binding.pinInput.setText("")
            }
        }
    }

    private fun tryBiometrics() {
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    setResult(RESULT_OK)
                    finish()
                }
            })
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(getString(R.string.lock_biometrics_prompt))
            .setSubtitle(getString(R.string.lock_biometrics_subtitle))
            .setNegativeButtonText(getString(R.string.lock_use_pin))
            .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_WEAK)
            .build()
        prompt.authenticate(info)
    }

    private fun sha256(s: String): String {
        val md = MessageDigest.getInstance("SHA-256")
        val bytes = md.digest(s.toByteArray(Charsets.UTF_8))
        return android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
    }
}
