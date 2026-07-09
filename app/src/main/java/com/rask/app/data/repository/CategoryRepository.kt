package com.rask.app.data.repository

import com.rask.app.data.db.RaskDatabase
import com.rask.app.data.db.entity.CategoryEntity
import kotlinx.coroutines.flow.Flow

class CategoryRepository(private val db: RaskDatabase) {

    private val dao = db.categoryDao()

    fun observeActive(): Flow<List<CategoryEntity>> = dao.observeActive()

    suspend fun all(): List<CategoryEntity> = dao.all()

    suspend fun byId(id: Long): CategoryEntity? = dao.byId(id)

    suspend fun byName(name: String): CategoryEntity? = dao.byName(name)

    suspend fun upsert(category: CategoryEntity): Long = dao.insert(category)

    suspend fun update(category: CategoryEntity) = dao.update(category)

    suspend fun delete(id: Long) = dao.deleteById(id)

    /**
     * Ensure the default starter categories exist on first launch.
     * Idempotent — safe to call every cold start.
     */
    suspend fun seedDefaultsIfEmpty(defaults: List<CategoryEntity>) {
        if (dao.count() > 0) return
        dao.insertAll(defaults)
    }
}
