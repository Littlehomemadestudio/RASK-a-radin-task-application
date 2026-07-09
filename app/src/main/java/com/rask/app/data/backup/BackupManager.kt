package com.rask.app.data.backup

import android.content.Context
import com.rask.app.data.db.RaskDatabase
import com.rask.app.data.db.entity.ActivityEntity
import com.rask.app.data.db.entity.CategoryEntity
import com.rask.app.data.db.entity.GoalEntity
import com.rask.app.data.db.entity.StreakEntity
import com.rask.app.data.db.entity.TemplateEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec
import javax.crypto.spec.PBEKeySpec

/**
 * Encrypted backup format: AES-256-CBC + PBKDF2-HMAC-SHA256 key derivation.
 *
 * File layout (binary):
 *   [16-byte salt] [16-byte IV] [AES-256-CBC(payload JSON)]
 *
 * Payload JSON is a [BackupPayload] snapshot of every table.
 * Restore is symmetric: decrypt, parse, wipe DB, insert.
 *
 * We use [org.json] (bundled with Android) to avoid pulling in
 * kotlinx-serialization — keeps APK smaller.
 */
class BackupManager(private val db: RaskDatabase) {

    /**
     * Export the entire DB to [out], encrypted with [password].
     * Caller is responsible for closing the stream.
     */
    suspend fun export(out: OutputStream, password: CharArray) = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("schemaVersion", 1)
            put("createdAt", System.currentTimeMillis())
            put("activities", activitiesToJsonArray(db.activityDao().all()))
            put("categories", categoriesToJsonArray(db.categoryDao().all()))
            put("goals", goalsToJsonArray(db.goalDao().all()))
            put("templates", templatesToJsonArray(db.templateDao().all()))
            put("streaks", streaksToJsonArray(db.streakDao().all()))
        }
        val plain = payload.toString().toByteArray(Charsets.UTF_8)

        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        val iv = ByteArray(16).also { SecureRandom().nextBytes(it) }
        val key = deriveKey(password, salt)

        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), IvParameterSpec(iv))
        val encrypted = cipher.doFinal(plain)

        out.write(salt)
        out.write(iv)
        out.write(encrypted)
        out.flush()
    }

    /**
     * Import + restore. Returns true on success, false on wrong password or corruption.
     */
    suspend fun import(input: InputStream, password: CharArray): Boolean = withContext(Dispatchers.IO) {
        try {
            val salt = input.readN(16)
            val iv = input.readN(16)
            val encrypted = input.readBytes()

            val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(deriveKey(password, salt), "AES"), IvParameterSpec(iv))
            val plain = cipher.doFinal(encrypted)
            val json = JSONObject(String(plain, Charsets.UTF_8))

            val activities = jsonArrayToActivities(json.optJSONArray("activities"))
            val categories = jsonArrayToCategories(json.optJSONArray("categories"))
            val goals = jsonArrayToGoals(json.optJSONArray("goals"))
            val templates = jsonArrayToTemplates(json.optJSONArray("templates"))
            val streaks = jsonArrayToStreaks(json.optJSONArray("streaks"))

            db.runInTransaction {
                db.activityDao().deleteAll()
                db.categoryDao().deleteAll()
                db.goalDao().deleteAll()
                db.templateDao().deleteAll()
                db.streakDao().deleteAll()

                if (activities.isNotEmpty()) db.activityDao().insertAll(activities)
                if (categories.isNotEmpty()) db.categoryDao().insertAll(categories)
                if (goals.isNotEmpty()) db.goalDao().insertAll(goals)
                if (templates.isNotEmpty()) db.templateDao().insertAll(templates)
                if (streaks.isNotEmpty()) db.streakDao().upsertAll(streaks)
            }
            true
        } catch (t: Throwable) {
            false
        }
    }

    // ---------- JSON encoding ----------

    private fun activitiesToJsonArray(items: List<ActivityEntity>): JSONArray = JSONArray().apply {
        items.forEach { a ->
            put(JSONObject().apply {
                put("id", a.id)
                put("title", a.title)
                put("startedAt", a.startedAt)
                put("endedAt", a.endedAt)
                put("durationMillis", a.durationMillis)
                put("category", a.category ?: JSONObject.NULL)
                put("tag", a.tag ?: JSONObject.NULL)
                put("notes", a.notes ?: JSONObject.NULL)
                put("color", a.color ?: JSONObject.NULL)
                put("isTimed", a.isTimed)
                put("createdAt", a.createdAt)
            })
        }
    }

    private fun categoriesToJsonArray(items: List<CategoryEntity>): JSONArray = JSONArray().apply {
        items.forEach { c ->
            put(JSONObject().apply {
                put("id", c.id)
                put("name", c.name)
                put("color", c.color)
                put("sortOrder", c.sortOrder)
                put("archived", c.archived)
                put("createdAt", c.createdAt)
            })
        }
    }

    private fun goalsToJsonArray(items: List<GoalEntity>): JSONArray = JSONArray().apply {
        items.forEach { g ->
            put(JSONObject().apply {
                put("id", g.id)
                put("scope", g.scope)
                put("targetMillis", g.targetMillis)
                put("categoryId", g.categoryId ?: JSONObject.NULL)
                put("name", g.name ?: JSONObject.NULL)
                put("active", g.active)
                put("createdAt", g.createdAt)
            })
        }
    }

    private fun templatesToJsonArray(items: List<TemplateEntity>): JSONArray = JSONArray().apply {
        items.forEach { t ->
            put(JSONObject().apply {
                put("id", t.id)
                put("name", t.name)
                put("defaultMillis", t.defaultMillis)
                put("category", t.category ?: JSONObject.NULL)
                put("tag", t.tag ?: JSONObject.NULL)
                put("color", t.color ?: JSONObject.NULL)
                put("sortOrder", t.sortOrder)
                put("createdAt", t.createdAt)
            })
        }
    }

    private fun streaksToJsonArray(items: List<StreakEntity>): JSONArray = JSONArray().apply {
        items.forEach { s ->
            put(JSONObject().apply {
                put("id", s.id)
                put("goalId", s.goalId)
                put("current", s.current)
                put("best", s.best)
                put("lastHitAt", s.lastHitAt ?: JSONObject.NULL)
                put("updatedAt", s.updatedAt)
            })
        }
    }

    // ---------- JSON decoding ----------

    private fun jsonArrayToActivities(arr: JSONArray?): List<ActivityEntity> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            ActivityEntity(
                id = o.optLong("id", 0),
                title = o.optString("title"),
                startedAt = o.optString("startedAt"),
                endedAt = o.optString("endedAt"),
                durationMillis = o.optLong("durationMillis", 0),
                category = o.optString("category").ifBlank { null },
                tag = o.optString("tag").ifBlank { null },
                notes = o.optString("notes").ifBlank { null },
                color = o.optString("color").ifBlank { null },
                isTimed = o.optBoolean("isTimed", false),
                createdAt = o.optLong("createdAt", System.currentTimeMillis())
            )
        }
    }

    private fun jsonArrayToCategories(arr: JSONArray?): List<CategoryEntity> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            CategoryEntity(
                id = o.optLong("id", 0),
                name = o.optString("name"),
                color = o.optString("color", "#D4AF37"),
                sortOrder = o.optInt("sortOrder", 0),
                archived = o.optBoolean("archived", false),
                createdAt = o.optLong("createdAt", System.currentTimeMillis())
            )
        }
    }

    private fun jsonArrayToGoals(arr: JSONArray?): List<GoalEntity> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            GoalEntity(
                id = o.optLong("id", 0),
                scope = o.optString("scope", "DAILY"),
                targetMillis = o.optLong("targetMillis", 0),
                categoryId = if (o.isNull("categoryId")) null else o.optLong("categoryId"),
                name = if (o.isNull("name")) null else o.optString("name"),
                active = o.optBoolean("active", true),
                createdAt = o.optLong("createdAt", System.currentTimeMillis())
            )
        }
    }

    private fun jsonArrayToTemplates(arr: JSONArray?): List<TemplateEntity> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            TemplateEntity(
                id = o.optLong("id", 0),
                name = o.optString("name"),
                defaultMillis = o.optLong("defaultMillis", 0),
                category = o.optString("category").ifBlank { null },
                tag = o.optString("tag").ifBlank { null },
                color = o.optString("color").ifBlank { null },
                sortOrder = o.optInt("sortOrder", 0),
                createdAt = o.optLong("createdAt", System.currentTimeMillis())
            )
        }
    }

    private fun jsonArrayToStreaks(arr: JSONArray?): List<StreakEntity> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            StreakEntity(
                id = o.optLong("id", 0),
                goalId = o.optLong("goalId", 0),
                current = o.optInt("current", 0),
                best = o.optInt("best", 0),
                lastHitAt = if (o.isNull("lastHitAt")) null else o.optString("lastHitAt"),
                updatedAt = o.optLong("updatedAt", System.currentTimeMillis())
            )
        }
    }

    // ---------- Helpers ----------

    private fun InputStream.readN(n: Int): ByteArray {
        val out = ByteArray(n)
        var read = 0
        while (read < n) {
            val r = this.read(out, read, n - read)
            if (r <= 0) break
            read += r
        }
        if (read != n) throw IllegalStateException("unexpected EOF")
        return out
    }

    private fun deriveKey(password: CharArray, salt: ByteArray): ByteArray {
        val spec = PBEKeySpec(password, salt, 200_000, 256)
        val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        return factory.generateSecret(spec).encoded
    }

    companion object {
        fun backupDir(context: Context): File =
            File(context.getExternalFilesDir(null), "backups").apply { if (!exists()) mkdirs() }

        fun defaultBackupFile(context: Context): File =
            File(backupDir(context), "rask-backup-${System.currentTimeMillis()}.rask")
    }
}
