package com.rask.app.ui.splash

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.lifecycleScope
import com.rask.app.RaskApplication
import com.rask.app.data.db.entity.CategoryEntity
import com.rask.app.ui.main.MainActivity
import com.rask.app.ui.onboarding.OnboardingActivity
import com.rask.app.utils.LocaleHelper
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Splash + router.
 *
 * 1. Honors Android 12+ SplashScreen API (animated icon); falls back gracefully on older.
 * 2. Ensures default categories are seeded.
 * 3. Decides whether to route to Onboarding (first launch) or MainActivity.
 * 4. Applies the saved locale *before* any UI inflates.
 */
class SplashActivity : AppCompatActivity() {

    override fun attachBaseContext(newBase: android.content.Context) {
        // Apply saved locale as early as possible so the very first activity
        // inflates with the correct language + RTL direction.
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        // Splash screen API — must be called before super.onCreate
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)

        // Keep splash visible while we bootstrap (max ~1.2s)
        var ready = false
        splash.setKeepOnScreenCondition { !ready }

        lifecycleScope.launch {
            val app = application as RaskApplication

            // Seed default categories if empty
            app.categoryRepo.seedDefaultsIfEmpty(defaultCategories())

            // Recompute streaks (cheap if no goals)
            app.goalRepo.recomputeAll()

            // Apply saved locale (so first activity inflates correctly)
            com.rask.app.utils.LocaleHelper.applyFromPrefs(app.prefs)

            // Decide routing
            val onboardingDone = app.prefs.onboardingCompleted.first()
            val appLockEnabled = app.prefs.appLockEnabled.first()
            delay(300) // small graceful delay so the splash reads as intentional
            ready = true

            val target = if (!onboardingDone) {
                Intent(this@SplashActivity, OnboardingActivity::class.java)
            } else if (appLockEnabled) {
                // Route through lock gate first
                val lockIntent = Intent(this@SplashActivity, com.rask.app.ui.settings.LockActivity::class.java)
                startActivity(lockIntent)
                finish()
                return@launch
            } else {
                Intent(this@SplashActivity, MainActivity::class.java)
            }
            startActivity(target)
            finish()
        }
    }

    private fun defaultCategories(): List<CategoryEntity> = listOf(
        CategoryEntity(name = getString(com.rask.app.R.string.category_work), color = "#D4AF37", sortOrder = 0),
        CategoryEntity(name = getString(com.rask.app.R.string.category_study), color = "#C9A84C", sortOrder = 1),
        CategoryEntity(name = getString(com.rask.app.R.string.category_exercise), color = "#A8C686", sortOrder = 2),
        CategoryEntity(name = getString(com.rask.app.R.string.category_reading), color = "#E6C66E", sortOrder = 3),
        CategoryEntity(name = getString(com.rask.app.R.string.category_meditation), color = "#9FB8D4", sortOrder = 4),
        CategoryEntity(name = getString(com.rask.app.R.string.category_hobby), color = "#E0B040", sortOrder = 5),
        CategoryEntity(name = getString(com.rask.app.R.string.category_other), color = "#7A7A82", sortOrder = 99)
    )
}
