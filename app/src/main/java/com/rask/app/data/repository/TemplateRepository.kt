package com.rask.app.data.repository

import com.rask.app.data.db.RaskDatabase
import com.rask.app.data.db.entity.TemplateEntity
import kotlinx.coroutines.flow.Flow

class TemplateRepository(private val db: RaskDatabase) {

    private val dao = db.templateDao()

    fun observeAll(): Flow<List<TemplateEntity>> = dao.observeAll()
    suspend fun all(): List<TemplateEntity> = dao.all()
    suspend fun byId(id: Long): TemplateEntity? = dao.byId(id)
    suspend fun upsert(t: TemplateEntity): Long = dao.insert(t)
    suspend fun update(t: TemplateEntity) = dao.update(t)
    suspend fun delete(id: Long) = dao.deleteById(id)
}
