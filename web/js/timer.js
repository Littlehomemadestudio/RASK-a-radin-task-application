// timer.js — Background stopwatch with localStorage persistence.
// Survives page reloads / app close: state is re-derived on each tick from
// stored start timestamp + accumulated elapsed.
window.RaskTimer = (function () {
  const KEY = "rask.timer";
  let listeners = [];
  let tickHandle = null;

  function read() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); }
    catch (_) { return {}; }
  }
  function write(state) {
    localStorage.setItem(KEY, JSON.stringify(state));
  }

  function isRunning() { return !!read().running; }
  function elapsedSec() {
    const s = read();
    if (!s) return 0;
    let e = s.elapsed || 0;
    if (s.running && s.start_ts) {
      e += Math.floor((Date.now() - s.start_ts) / 1000);
    }
    return e;
  }
  function currentTitle() { return read().title || ""; }
  function currentCategoryId() { return read().category_id || null; }
  function currentTemplateId() { return read().template_id || null; }

  function start(title, categoryId, templateId) {
    if (isRunning()) return;
    write({
      running: true,
      title: title || "",
      category_id: categoryId || null,
      template_id: templateId || null,
      start_ts: Date.now(),
      elapsed: read().elapsed || 0,
    });
    _startTick();
    _emit();
    _notify();
  }
  function pause() {
    if (!isRunning()) return;
    const s = read();
    write({ ...s, running: false, start_ts: null, elapsed: elapsedSec() });
    _emit();
    _notify();
  }
  function resume() {
    if (isRunning()) return;
    const s = read();
    write({ ...s, running: true, start_ts: Date.now() });
    _startTick();
    _emit();
    _notify();
  }
  async function stopAndSave() {
    const s = read();
    const total = elapsedSec();
    write({});
    _emit();
    _notify();

    if (total < 5) return null;

    const now = new Date();
    const start = new Date(now.getTime() - total * 1000);
    const a = {
      title: s.title || "(no title)",
      category_id: s.category_id || null,
      kind: "stopwatch",
      date_iso: now.toISOString().slice(0, 10),
      start_iso: start.toISOString().slice(0, 19),
      end_iso: now.toISOString().slice(0, 19),
      duration_sec: total,
      note: "",
      template_id: s.template_id || null,
      voice_input: 0,
      created_at: now.toISOString(),
    };
    const id = await window.RaskDB.insertActivity(a);
    await checkGoalsAfterSave(a);
    return id;
  }
  function cancel() {
    write({});
    _emit();
    _notify();
  }

  function addListener(cb) { listeners.push(cb); }
  function removeListener(cb) { listeners = listeners.filter((x) => x !== cb); }
  function _emit() {
    const e = elapsedSec(), r = isRunning();
    listeners.forEach((cb) => { try { cb(e, r); } catch (_) {} });
  }
  function _startTick() {
    if (tickHandle) clearInterval(tickHandle);
    tickHandle = setInterval(() => {
      if (!isRunning()) { clearInterval(tickHandle); tickHandle = null; return; }
      _emit();
      _notify();
    }, 1000);
  }

  // === Goal & streak check ===
  async function checkGoalsAfterSave(activity) {
    const goals = await window.RaskDB.allGoals(true);
    const today = new Date(activity.date_iso + "T00:00:00");
    for (const g of goals) {
      if (g.category_id && g.category_id !== activity.category_id) continue;
      let start, end;
      if (g.period === "daily") { start = today; end = today; }
      else if (g.period === "weekly") {
        start = window.DateUtils.startOfWeek(today);
        end = window.DateUtils.endOfWeek(today);
      } else {
        start = window.DateUtils.startOfMonth(today);
        end = window.DateUtils.endOfMonth(today);
      }
      const total = await window.RaskDB.totalSecondsBetween(
        start.toISOString().slice(0, 10),
        end.toISOString().slice(0, 10),
        g.category_id
      );
      const target = g.target_minutes * 60;
      if (total >= target) {
        await bumpStreak(g, today);
      }
    }
  }
  async function bumpStreak(goal, today) {
    let st = await window.RaskDB.streakForGoal(goal.id);
    const todayISO = today.toISOString().slice(0, 10);
    if (!st) {
      st = { goal_id: goal.id, current: 1, longest: 1, last_hit_date: todayISO };
      await window.RaskDB.upsertStreak(st);
      return;
    }
    if (st.last_hit_date === todayISO) {
      if (st.current > st.longest) { st.longest = st.current; await window.RaskDB.upsertStreak(st); }
      return;
    }
    let last = st.last_hit_date ? new Date(st.last_hit_date + "T00:00:00") : null;
    const diff = last ? Math.round((today - last) / 86400000) : -1;
    st.current = (diff === 1) ? st.current + 1 : 1;
    if (st.current > st.longest) st.longest = st.current;
    st.last_hit_date = todayISO;
    await window.RaskDB.upsertStreak(st);
    // Badges
    if (st.current === 3) await window.RaskDB.awardBadge("streak_3", "3-day streak", window.t("streak3"));
    if (st.current === 7) await window.RaskDB.awardBadge("streak_7", "7-day streak", window.t("streak7"));
    if (st.current === 30) await window.RaskDB.awardBadge("streak_30", "30-day streak", window.t("streak30"));
    if (st.current === 100) await window.RaskDB.awardBadge("streak_100", "100-day streak", window.t("streak100"));
  }

  // === Notifications (live timer + reminders) ===
  let _notifPermissionAsked = false;
  async function _notify() {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") {
      if (!_notifPermissionAsked && isRunning()) {
        _notifPermissionAsked = true;
        try { await Notification.requestPermission(); } catch (_) {}
      }
      return;
    }
    // Use the persistent service-worker notification if available
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      // Defer to app.js to keep SW message format in one place
      // (we post a message; app.js forwards it to SW if needed)
    }
    // Update visible title (browser tab) — good proxy for active timer
    if (isRunning()) {
      const e = elapsedSec();
      const h = Math.floor(e / 3600), m = Math.floor((e % 3600) / 60), s = e % 60;
      const txt = `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")} — ${currentTitle() || "Rask"}`;
      document.title = txt;
    } else {
      document.title = "Rask";
    }
  }

  // Resume ticking on load if we were running
  document.addEventListener("DOMContentLoaded", () => {
    if (isRunning()) _startTick();
  });

  return {
    isRunning, elapsedSec, currentTitle, currentCategoryId, currentTemplateId,
    start, pause, resume, stopAndSave, cancel,
    addListener, removeListener,
    checkGoalsAfterSave,
  };
})();
