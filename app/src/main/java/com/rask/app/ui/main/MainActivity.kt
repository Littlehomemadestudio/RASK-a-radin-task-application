package com.rask.app.ui.main

import android.content.Intent
import android.os.Bundle
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.navigation.findNavController
import androidx.navigation.ui.setupWithNavController
import com.rask.app.R
import com.rask.app.RaskApplication
import com.rask.app.databinding.ActivityMainBinding
import com.rask.app.ui.home.QuickLogActivity
import com.rask.app.utils.LocaleHelper
import kotlinx.coroutines.launch

/**
 * Main host — bottom-nav + FAB + fragment container.
 *
 * Back-press: if not on Home, return to Home. If on Home, behave normally
 * (move task to back) — preserves app state.
 *
 * App lock: if the user has enabled it, we route through LockActivity on
 * cold start. This is done from [SplashActivity] when app-lock is on.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun attachBaseContext(newBase: android.content.Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Wire bottom nav to NavController
        val navController = findNavController(R.id.nav_host)
        binding.bottomNav.setupWithNavController(navController)

        // FAB launches QuickLog overlay
        binding.fabQuickLog.setOnClickListener {
            startActivity(Intent(this, QuickLogActivity::class.java))
        }

        // Subtle gold pulse on the FAB — only when on Home tab
        navController.addOnDestinationChangedListener { _, dest, _ ->
            if (dest.id == R.id.nav_home) {
                binding.fabQuickLog.animate()
                    .scaleX(1.04f).scaleY(1.04f).setDuration(900)
                    .withEndAction {
                        binding.fabQuickLog.animate().scaleX(1f).scaleY(1f).setDuration(900).start()
                    }.start()
            }
        }

        // Custom back handling
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (navController.currentDestination?.id != R.id.nav_home) {
                    navController.navigate(R.id.nav_home)
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }

    override fun onResume() {
        super.onResume()
        // Recompute streaks when the user comes back to the app
        val app = application as RaskApplication
        lifecycleScope.launch { app.goalRepo.recomputeAll() }
    }
}
