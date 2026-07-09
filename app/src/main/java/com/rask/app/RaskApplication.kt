package com.rask.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.work.Configuration
import androidx.work.WorkManager
import com.rask.app.data.db.RaskDatabase
import com.rask.app.data.prefs.PreferenceManager
import com.rask.app.data.repository.ActivityRepository
import com.rask.app.data.repository.CategoryRepository
import com.rask.app.data.repository.GoalRepository
import com.rask.app.data.repository.TemplateRepository
import com.rask.app.data.backup.BackupManager
import com.rask.app.utils.NotificationHelper

/**
 * Application entry-point.
 *
 * Responsibilities:
 *  - Create notification channels early (Android 8+ requirement)
 *  - Initialise WorkManager manually (we disabled its default initializer in the manifest
 *    so we can theme + bind to our DI graph later)
 *  - Provide a tiny service-locator for repos (no DI framework to keep deps minimal)
 */
class RaskApplication : Application(), Configuration.Provider {

    lateinit var prefs: PreferenceManager
        private set

    lateinit var db: RaskDatabase
        private set

    lateinit var activityRepo: ActivityRepository
        private set
    lateinit var categoryRepo: CategoryRepository
        private set
    lateinit var goalRepo: GoalRepository
        private set
    lateinit var templateRepo: TemplateRepository
        private set
    lateinit var backupManager: BackupManager
        private set

    override fun onCreate() {
        super.onCreate()

        // ===== Database =====
        db = RaskDatabase.get(this)

        // ===== Repositories =====
        prefs = PreferenceManager(this)
        activityRepo = ActivityRepository(db)
        categoryRepo = CategoryRepository(db)
        templateRepo = TemplateRepository(db)
        goalRepo = GoalRepository(db, activityRepo)
        backupManager = BackupManager(db)

        // ===== Notification channels =====
        NotificationHelper.createChannels(this)

        // ===== WorkManager (manual init) =====
        WorkManager.initialize(this, workManagerConfiguration)
    }

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setMinimumLoggingLevel(android.util.Log.INFO)
            .build()

    companion object {
        fun get(context: Context): RaskApplication =
            context.applicationContext as RaskApplication
    }
}
