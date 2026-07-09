package com.rask.app.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.rask.app.data.db.converters.Converters
import com.rask.app.data.db.dao.ActivityDao
import com.rask.app.data.db.dao.CategoryDao
import com.rask.app.data.db.dao.GoalDao
import com.rask.app.data.db.dao.StreakDao
import com.rask.app.data.db.dao.TemplateDao
import com.rask.app.data.db.entity.ActivityEntity
import com.rask.app.data.db.entity.CategoryEntity
import com.rask.app.data.db.entity.GoalEntity
import com.rask.app.data.db.entity.StreakEntity
import com.rask.app.data.db.entity.TemplateEntity

/**
 * The single Room database for Rask.
 *
 * Versioned for future migrations. Bump [version] + add a [Migration] when the
 * schema changes — schemas are auto-exported to /schemas for testing.
 */
@Database(
    entities = [
        ActivityEntity::class,
        CategoryEntity::class,
        GoalEntity::class,
        StreakEntity::class,
        TemplateEntity::class
    ],
    version = 1,
    exportSchema = true
)
@TypeConverters(Converters::class)
abstract class RaskDatabase : RoomDatabase() {

    abstract fun activityDao(): ActivityDao
    abstract fun categoryDao(): CategoryDao
    abstract fun goalDao(): GoalDao
    abstract fun templateDao(): TemplateDao
    abstract fun streakDao(): StreakDao

    companion object {
        @Volatile private var INSTANCE: RaskDatabase? = null

        fun get(context: Context): RaskDatabase =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: build(context).also { INSTANCE = it }
            }

        private fun build(context: Context): RaskDatabase =
            Room.databaseBuilder(
                context.applicationContext,
                RaskDatabase::class.java,
                "rask.db"
            )
                // Strict mode in debug to catch main-thread IO.
                .fallbackToDestructiveMigrationOnDowngrade()
                .build()

        /**
         * Close + wipe the database. Used by "Clear all data" in Settings and
         * by Restore (which deletes everything before re-inserting).
         */
        suspend fun clear(context: Context) {
            val db = get(context)
            db.activityDao().deleteAll()
            db.categoryDao().deleteAll()
            db.goalDao().deleteAll()
            db.templateDao().deleteAll()
            db.streakDao().deleteAll()
        }
    }
}
