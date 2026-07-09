package com.rask.app.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.rask.app.data.db.entity.StreakEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface StreakDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(streak: StreakEntity): Long

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(streaks: List<StreakEntity>): List<Long>

    @Query("DELETE FROM streaks WHERE goal_id = :goalId")
    suspend fun deleteByGoal(goalId: Long)

    @Query("DELETE FROM streaks")
    suspend fun deleteAll()

    @Query("SELECT * FROM streaks WHERE goal_id = :goalId LIMIT 1")
    suspend fun byGoal(goalId: Long): StreakEntity?

    @Query("SELECT * FROM streaks")
    fun observeAll(): Flow<List<StreakEntity>>

    @Query("SELECT * FROM streaks")
    suspend fun all(): List<StreakEntity>
}
