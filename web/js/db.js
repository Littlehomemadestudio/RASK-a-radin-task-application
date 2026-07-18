// db.js — IndexedDB wrapper for Rask (replaces SQLite/Room).
// Schema: activities, categories, goals, streaks, templates, badges, kv.
window.RaskDB = (function () {
  const DB_NAME = "rask-db";
  const DB_VERSION = 1;
  const STORES = ["activities", "categories", "goals", "streaks", "templates", "badges", "kv"];
  let _db = null;

  function open() {
    return new Promise((resolve, reject) => {
      if (_db) return resolve(_db);
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains("activities")) {
          const s = db.createObjectStore("activities", { keyPath: "id", autoIncrement: true });
          s.createIndex("date_iso", "date_iso", { unique: false });
          s.createIndex("category_id", "category_id", { unique: false });
          s.createIndex("kind", "kind", { unique: false });
          s.createIndex("created_at", "created_at", { unique: false });
        }
        if (!db.objectStoreNames.contains("categories")) {
          const s = db.createObjectStore("categories", { keyPath: "id", autoIncrement: true });
          s.createIndex("key", "key", { unique: true });
        }
        if (!db.objectStoreNames.contains("goals")) {
          db.createObjectStore("goals", { keyPath: "id", autoIncrement: true });
        }
        if (!db.objectStoreNames.contains("streaks")) {
          db.createObjectStore("streaks", { keyPath: "id", autoIncrement: true });
        }
        if (!db.objectStoreNames.contains("templates")) {
          db.createObjectStore("templates", { keyPath: "id", autoIncrement: true });
        }
        if (!db.objectStoreNames.contains("badges")) {
          const s = db.createObjectStore("badges", { keyPath: "id", autoIncrement: true });
          s.createIndex("key", "key", { unique: true });
        }
        if (!db.objectStoreNames.contains("kv")) {
          db.createObjectStore("kv", { keyPath: "key" });
        }
      };
      req.onsuccess = (e) => {
        _db = e.target.result;
        seedDefaults(_db).then(() => resolve(_db)).catch(reject);
      };
      req.onerror = () => reject(req.error);
    });
  }

  function seedDefaults(db) {
    return new Promise((resolve) => {
      const tx = db.transaction("categories", "readonly");
      const countReq = tx.objectStore("categories").count();
      countReq.onsuccess = () => {
        if (countReq.result > 0) return resolve();
        const defaults = [
          { key: "FOCUS", color: "#D4AF37", name_en: "Focus", name_fa: "تمرکز", icon: "ring", order_index: 0, archived: 0 },
          { key: "LEARN", color: "#7B9BC9", name_en: "Learn", name_fa: "یادگیری", icon: "book", order_index: 1, archived: 0 },
          { key: "WORK", color: "#C9A84C", name_en: "Work", name_fa: "کار", icon: "briefcase", order_index: 2, archived: 0 },
          { key: "HEALTH", color: "#7BC97B", name_en: "Health", name_fa: "سلامتی", icon: "heart", order_index: 3, archived: 0 },
          { key: "CREATIVE", color: "#D49ABF", name_en: "Creative", name_fa: "خلاقیت", icon: "palette", order_index: 4, archived: 0 },
          { key: "SOCIAL", color: "#E8B85A", name_en: "Social", name_fa: "اجتماعی", icon: "users", order_index: 5, archived: 0 },
          { key: "REST", color: "#9A9A9F", name_en: "Rest", name_fa: "استراحت", icon: "moon", order_index: 6, archived: 0 },
        ];
        const tx2 = db.transaction(["categories", "goals", "kv"], "readwrite");
        defaults.forEach((c) => tx2.objectStore("categories").add(c));
        // Default daily goal: 120 minutes
        tx2.objectStore("goals").add({
          period: "daily", category_id: null, target_minutes: 120, active: 1, created_at: new Date().toISOString()
        });
        tx2.objectStore("kv").put({ key: "first_run", value: "1" });
        tx2.oncomplete = () => resolve();
        tx2.onerror = () => resolve();
      };
      countReq.onerror = () => resolve();
    });
  }

  function tx(store, mode) { return _db.transaction(store, mode).objectStore(store); }

  function _reqToPromise(req) {
    return new Promise((resolve, reject) => {
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  // === Generic CRUD ===
  async function add(store, obj) {
    await open();
    return new Promise((resolve, reject) => {
      const r = _db.transaction(store, "readwrite").objectStore(store).add(obj);
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
  }
  async function put(store, obj) {
    await open();
    return new Promise((resolve, reject) => {
      const r = _db.transaction(store, "readwrite").objectStore(store).put(obj);
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
  }
  async function del(store, id) {
    await open();
    return new Promise((resolve, reject) => {
      const r = _db.transaction(store, "readwrite").objectStore(store).delete(id);
      r.onsuccess = () => resolve();
      r.onerror = () => reject(r.error);
    });
  }
  async function get(store, id) {
    await open();
    return _reqToPromise(tx(store, "readonly").get(id));
  }
  async function all(store) {
    await open();
    return _reqToPromise(tx(store, "readonly").getAll());
  }
  async function getByIndex(store, indexName, value) {
    await open();
    return _reqToPromise(tx(store, "readonly").index(indexName).get(value));
  }

  // === KV store ===
  async function kvGet(key, def) {
    await open();
    const r = await _reqToPromise(tx("kv", "readonly").get(key));
    return r ? r.value : def;
  }
  async function kvSet(key, value) {
    await open();
    return new Promise((resolve, reject) => {
      const r = _db.transaction("kv", "readwrite").objectStore("kv").put({ key, value });
      r.onsuccess = () => resolve();
      r.onerror = () => reject(r.error);
    });
  }
  async function kvGetBool(key, def) {
    const v = await kvGet(key, def ? "1" : "0");
    return v === "1" || v === true;
  }
  async function kvGetJSON(key, def) {
    const v = await kvGet(key, null);
    if (v == null) return def;
    try { return JSON.parse(v); } catch (_) { return def; }
  }
  async function kvSetJSON(key, obj) {
    return kvSet(key, JSON.stringify(obj));
  }

  // === Activities ===
  async function insertActivity(a) {
    if (!a.created_at) a.created_at = new Date().toISOString();
    return add("activities", a);
  }
  async function updateActivity(a) { return put("activities", a); }
  async function deleteActivity(id) { return del("activities", id); }
  async function getActivity(id) { return get("activities", id); }
  async function allActivities() { return all("activities"); }
  async function recentActivities(limit) {
    const all = await allActivities();
    return all.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "")).slice(0, limit || 20);
  }
  async function activitiesByDateRange(startISO, endISO) {
    const all = await allActivities();
    return all.filter((a) => a.date_iso >= startISO && a.date_iso <= endISO)
              .sort((a, b) => (b.date_iso || "").localeCompare(a.date_iso || ""));
  }
  async function activitiesByDate(dateISO) {
    const all = await allActivities();
    return all.filter((a) => a.date_iso === dateISO);
  }
  async function totalSecondsBetween(startISO, endISO, categoryId) {
    const all = await activitiesByDateRange(startISO, endISO);
    return all
      .filter((a) => !categoryId || a.category_id === categoryId)
      .reduce((s, a) => s + (a.duration_sec || 0), 0);
  }
  async function totalSecondsOn(dateISO, categoryId) {
    const all = await activitiesByDate(dateISO);
    return all
      .filter((a) => !categoryId || a.category_id === categoryId)
      .reduce((s, a) => s + (a.duration_sec || 0), 0);
  }
  async function secondsPerDay(startISO, endISO, categoryId) {
    const all = await activitiesByDateRange(startISO, endISO);
    const map = {};
    all.forEach((a) => {
      if (categoryId && a.category_id !== categoryId) return;
      map[a.date_iso] = (map[a.date_iso] || 0) + (a.duration_sec || 0);
    });
    return map;
  }
  async function secondsPerCategory(startISO, endISO) {
    const all = await activitiesByDateRange(startISO, endISO);
    const map = {};
    all.forEach((a) => {
      const cid = a.category_id || 0;
      map[cid] = (map[cid] || 0) + (a.duration_sec || 0);
    });
    return Object.entries(map).map(([cid, sec]) => [parseInt(cid, 10) || 0, sec])
      .sort((a, b) => b[1] - a[1]);
  }
  async function secondsPerHour(dateISO) {
    const all = await activitiesByDate(dateISO);
    const buckets = new Array(24).fill(0);
    all.forEach((a) => {
      const ts = a.start_iso || a.created_at;
      if (!ts) return;
      const h = new Date(ts).getHours();
      if (h >= 0 && h < 24) buckets[h] += a.duration_sec || 0;
    });
    return buckets;
  }

  // === Categories ===
  async function allCategories(includeArchived) {
    const all = await all("categories");
    const list = all.sort((a, b) => (a.order_index || 0) - (b.order_index || 0));
    return includeArchived ? list : list.filter((c) => !c.archived);
  }
  async function categoryById(id) { return id ? get("categories", id) : null; }
  async function upsertCategory(c) {
    if (c.id) return put("categories", c);
    return add("categories", c);
  }
  async function archiveCategory(id) {
    const c = await get("categories", id);
    if (c) { c.archived = 1; return put("categories", c); }
  }

  // === Goals ===
  async function allGoals(activeOnly) {
    const all = await all("goals");
    return activeOnly ? all.filter((g) => g.active) : all;
  }
  async function upsertGoal(g) {
    if (!g.created_at) g.created_at = new Date().toISOString();
    if (g.id) return put("goals", g);
    return add("goals", g);
  }
  async function deleteGoal(id) { return del("goals", id); }

  // === Streaks ===
  async function streakForGoal(goalId) {
    const all = await all("streaks");
    return all.find((s) => s.goal_id === goalId) || null;
  }
  async function upsertStreak(s) {
    if (s.id) return put("streaks", s);
    return add("streaks", s);
  }
  async function topStreaks(limit) {
    const all = await all("streaks");
    return all.sort((a, b) => (b.longest || 0) - (a.longest || 0)).slice(0, limit || 10);
  }

  // === Templates ===
  async function allTemplates() { return all("templates"); }
  async function upsertTemplate(t) {
    if (!t.created_at) t.created_at = new Date().toISOString();
    if (t.id) return put("templates", t);
    return add("templates", t);
  }
  async function deleteTemplate(id) { return del("templates", id); }

  // === Badges ===
  async function allBadges() { return all("badges"); }
  async function hasBadge(key) {
    await open();
    const r = await _reqToPromise(tx("badges", "readonly").index("key").get(key));
    return !!r;
  }
  async function awardBadge(key, titleEn, titleFa) {
    if (await hasBadge(key)) return;
    return add("badges", { key, title_en: titleEn, title_fa: titleFa, earned_at: new Date().toISOString() });
  }

  // === Backup payload (used by backup.js) ===
  async function exportAll() {
    const result = {};
    for (const s of STORES) result[s] = await all(s);
    return result;
  }
  async function replaceAll(payload) {
    await open();
    return new Promise((resolve, reject) => {
      const tx = _db.transaction(STORES, "readwrite");
      STORES.forEach((s) => {
        tx.objectStore(s).clear();
        (payload[s] || []).forEach((row) => tx.objectStore(s).add(row));
      });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  return {
    open,
    // CRUD
    add, put, del, get, all,
    // KV
    kvGet, kvSet, kvGetBool, kvGetJSON, kvSetJSON,
    // Activities
    insertActivity, updateActivity, deleteActivity, getActivity,
    allActivities, recentActivities, activitiesByDateRange, activitiesByDate,
    totalSecondsBetween, totalSecondsOn,
    secondsPerDay, secondsPerCategory, secondsPerHour,
    // Categories
    allCategories, categoryById, upsertCategory, archiveCategory,
    // Goals
    allGoals, upsertGoal, deleteGoal,
    // Streaks
    streakForGoal, upsertStreak, topStreaks,
    // Templates
    allTemplates, upsertTemplate, deleteTemplate,
    // Badges
    allBadges, hasBadge, awardBadge,
    // Backup
    exportAll, replaceAll,
  };
})();
