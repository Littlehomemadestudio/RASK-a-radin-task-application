package com.rask.app.utils

import android.content.Context
import android.content.res.Configuration
import android.os.Build
import androidx.core.os.LocaleListCompat
import androidx.appcompat.app.AppCompatDelegate
import com.rask.app.data.prefs.PreferenceManager
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import java.util.Locale

/**
 * Locale + RTL handling.
 *
 * Strategy:
 *  - User can choose "system", "en", or "fa" in Settings.
 *  - The chosen locale is applied via [AppCompatDelegate.setApplicationLocales]
 *    (the official AndroidX AppCompat API that handles both per-app language
 *    on Android 13+ and graceful RTL direction flips on all versions).
 *  - Activities call [wrap] in [attachBaseContext] so the very first
 *    inflation uses the correct language.
 *
 * RTL is enabled via `android:supportsRtl="true"` in the manifest and
 * `android:textDirection="locale"` on TextViews. We also set the layout
 * direction explicitly in [wrap] for older devices.
 */
object LocaleHelper {

    const val SYSTEM = "system"
    const val ENGLISH = "en"
    const val PERSIAN = "fa"

    /** Sync the AppCompatDelegate locale with whatever is saved in DataStore. */
    fun applyFromPrefs(prefs: PreferenceManager) {
        val code = runBlocking { prefs.language.first() }
        apply(code)
    }

    fun apply(code: String) {
        val locales = when (code) {
            ENGLISH -> LocaleListCompat.forLanguageTags("en")
            PERSIAN -> LocaleListCompat.forLanguageTags("fa")
            else -> LocaleListCompat.getEmptyLocaleList() // follow system
        }
        AppCompatDelegate.setApplicationLocales(locales)
    }

    /**
     * Wrap a context so layout direction + locale are correct *before*
     * AppCompatActivity.onCreate runs.
     *
     * On API 17+ we explicitly set layoutDirection based on the locale's
     * directionality, since some OEMs don't honour android:supportsRtl
     * reliably.
     */
    fun wrap(base: Context): Context {
        val config = Configuration(base.resources.configuration)

        val locale = when (AppCompatDelegate.getApplicationLocales().get(0)) {
            null -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                    base.resources.configuration.locales[0]
                } else {
                    @Suppress("DEPRECATION")
                    base.resources.configuration.locale
                }
            }
            else -> AppCompatDelegate.getApplicationLocales().get(0)!!
        }

        // Force layoutDirection to match locale's natural direction
        val direction = android.text.TextUtils.getLayoutDirectionFromLocale(locale)
        config.layoutDirection = direction

        @Suppress("DEPRECATION")
        config.setLocale(locale)

        return base.createConfigurationContext(config)
    }

    fun isRtl(): Boolean {
        val locale = AppCompatDelegate.getApplicationLocales().get(0)
            ?: Locale.getDefault()
        return android.text.TextUtils.getLayoutDirectionFromLocale(locale) ==
            android.view.View.LAYOUT_DIRECTION_RTL
    }
}
