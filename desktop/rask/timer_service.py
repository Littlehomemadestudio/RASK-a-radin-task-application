"""timer_service.py — Background stopwatch with persistence (1:1 mirror of web/js/timer.js).

State is persisted in the KV store as JSON under config.TIMER_KV_KEY:
    {
      "running": bool,
      "title": str,
      "category_id": int|None,
      "template_id": int|None,
      "start_ts": float|None,    # Unix timestamp (seconds) when last resumed
      "elapsed": int,             # accumulated seconds before last resume
      "paused_at": float|None,    # timestamp when paused (for notifications)
    }

Listeners receive (elapsed_sec, running) on every tick and state change.

Goal & streak bumping is performed after a stopAndSave, mirroring timer.js
checkGoalsAfterSave + bumpStreak (including badge awards).
"""
from __future__ import annotations
import json
import threading
import time
import datetime as _dt
from typing import Callable, Optional

from . import config
from . import database
from .date_utils import today_iso, now_iso, start_of_week, end_of_week, start_of_month, end_of_month


# =====================================================================
# === STATE ===
# =====================================================================
_lock = threading.RLock()
_listeners: list[Callable[[int, bool], None]] = []
_tick_handle: Optional[int] = None
_root_widget = None  # set by app.py for tkinter.after scheduling


def _read_state() -> dict:
    """Read the persisted timer state from KV."""
    raw = database.kv_get(config.TIMER_KV_KEY)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _write_state(state: dict) -> None:
    """Persist timer state to KV."""
    database.kv_set(config.TIMER_KV_KEY, json.dumps(state, ensure_ascii=False))


# =====================================================================
# === QUERIES ===
# =====================================================================
def is_running() -> bool:
    """Return True if the timer is currently running."""
    return bool(_read_state().get("running"))


def elapsed_sec() -> int:
    """Return total elapsed seconds (including current run segment)."""
    s = _read_state()
    if not s:
        return 0
    e = int(s.get("elapsed", 0) or 0)
    if s.get("running") and s.get("start_ts"):
        e += int(time.time() - float(s["start_ts"]))
    return e


def current_title() -> str:
    """Return the title of the current timer."""
    return _read_state().get("title", "") or ""


def current_category_id() -> Optional[int]:
    """Return the category id of the current timer, or None."""
    v = _read_state().get("category_id")
    return int(v) if v else None


def current_template_id() -> Optional[int]:
    """Return the template id of the current timer, or None."""
    v = _read_state().get("template_id")
    return int(v) if v else None


def started_at() -> Optional[_dt.datetime]:
    """Return the datetime the current run segment started, or None."""
    s = _read_state()
    if not s.get("running") or not s.get("start_ts"):
        return None
    return _dt.datetime.fromtimestamp(float(s["start_ts"]))


def paused_at() -> Optional[_dt.datetime]:
    """Return the datetime the timer was last paused, or None."""
    s = _read_state()
    if not s.get("paused_at"):
        return None
    return _dt.datetime.fromtimestamp(float(s["paused_at"]))


# =====================================================================
# === ACTIONS ===
# =====================================================================
def start(title: str = "", category_id: Optional[int] = None,
          template_id: Optional[int] = None) -> None:
    """Start a new timer. If one is already running, do nothing."""
    with _lock:
        if is_running():
            return
        prev_elapsed = int(_read_state().get("elapsed", 0) or 0)
        _write_state({
            "running": True,
            "title": title or "",
            "category_id": category_id,
            "template_id": template_id,
            "start_ts": time.time(),
            "elapsed": prev_elapsed,
            "paused_at": None,
        })
        _start_tick()
        _emit()
        _notify()


def pause() -> None:
    """Pause the running timer. Accumulated time is preserved."""
    with _lock:
        s = _read_state()
        if not s.get("running"):
            return
        elapsed = elapsed_sec()
        _write_state({
            **s,
            "running": False,
            "start_ts": None,
            "elapsed": elapsed,
            "paused_at": time.time(),
        })
        _emit()
        _notify()


def resume() -> None:
    """Resume a paused timer."""
    with _lock:
        s = _read_state()
        if s.get("running"):
            return
        _write_state({
            **s,
            "running": True,
            "start_ts": time.time(),
            "paused_at": None,
        })
        _start_tick()
        _emit()
        _notify()


def stop_and_save() -> Optional[int]:
    """Stop the timer and save the accumulated time as an activity.
    
    Returns the new activity id, or None if the elapsed time was less than
    config.TIMER_MIN_SAVE_SEC seconds (5s).
    """
    with _lock:
        s = _read_state()
        total = elapsed_sec()
        _write_state({})
        _emit()
        _notify()
        if total < config.TIMER_MIN_SAVE_SEC:
            return None
        now = _dt.datetime.now()
        start_dt = now - _dt.timedelta(seconds=total)
        activity = {
            "title": s.get("title") or "(no title)",
            "category_id": s.get("category_id"),
            "kind": "stopwatch",
            "date_iso": now.strftime("%Y-%m-%d"),
            "start_iso": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_iso": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_sec": total,
            "note": "",
            "template_id": s.get("template_id"),
            "voice_input": 0,
            "created_at": now.isoformat(),
        }
        activity_id = database.insert_activity(activity)
        # Run goal/streak checks (may award badges)
        try:
            _check_goals_after_save(activity)
        except Exception:
            pass
        # Award milestone badges
        try:
            _check_milestone_badges()
        except Exception:
            pass
        return activity_id


def cancel() -> None:
    """Discard the current timer without saving."""
    with _lock:
        _write_state({})
        _emit()
        _notify()


def toggle() -> None:
    """Toggle between running and paused."""
    if is_running():
        pause()
    else:
        resume()


# =====================================================================
# === LISTENER MANAGEMENT ===
# =====================================================================
def add_listener(cb: Callable[[int, bool], None]) -> None:
    """Register a listener that receives (elapsed_sec, running) callbacks."""
    if cb not in _listeners:
        _listeners.append(cb)


def remove_listener(cb: Callable[[int, bool], None]) -> None:
    """Unregister a listener."""
    if cb in _listeners:
        _listeners.remove(cb)


def _emit() -> None:
    """Notify all listeners of the current state."""
    e = elapsed_sec()
    r = is_running()
    for cb in list(_listeners):
        try:
            cb(e, r)
        except Exception:
            pass


# =====================================================================
# === TICK LOOP ===
# =====================================================================
def _start_tick() -> None:
    """Start the periodic tick (every TIMER_TICK_MS_DESKTOP ms)."""
    global _tick_handle
    if _root_widget is not None:
        if _tick_handle is not None:
            try:
                _root_widget.after_cancel(_tick_handle)
            except Exception:
                pass
        _schedule_tick()
    # else: no UI — tick won't run, but state is still persisted


def _schedule_tick() -> None:
    """Schedule the next tick on the Tk main loop."""
    global _tick_handle
    if _root_widget is None:
        return
    _tick_handle = _root_widget.after(config.TIMER_TICK_MS_DESKTOP, _on_tick)


def _on_tick() -> None:
    """Called every second while the timer is running."""
    if not is_running():
        global _tick_handle
        _tick_handle = None
        return
    _emit()
    _notify()
    _schedule_tick()


def set_root(root) -> None:
    """Register the Tk root widget so ticks can be scheduled on the main loop."""
    global _root_widget
    _root_widget = root


def init_on_startup() -> None:
    """Resume ticking on app launch if the timer was running when we closed."""
    if is_running():
        _start_tick()


# =====================================================================
# === NOTIFICATIONS (desktop: update window title) ===
# =====================================================================
def _notify() -> None:
    """Update the window title to show the active timer (mirror timer.js _notify)."""
    if _root_widget is None:
        return
    try:
        if is_running():
            e = elapsed_sec()
            h = e // 3600
            m = (e % 3600) // 60
            s = e % 60
            txt = f"{h:02d}:{m:02d}:{s:02d} — {current_title() or 'Rask'}"
            _root_widget.title(txt)
        else:
            _root_widget.title(config.APP_NAME)
    except Exception:
        pass


# =====================================================================
# === GOAL & STREAK CHECKING (mirror timer.js checkGoalsAfterSave) ===
# =====================================================================
def _check_goals_after_save(activity: dict) -> None:
    """For each active goal, check if the target was met. Bump streaks & award badges."""
    from .i18n import t
    goals = database.all_goals(active_only=True)
    today = _dt.date.fromisoformat(activity["date_iso"])
    for g in goals:
        # Skip goals scoped to a different category
        if g.get("category_id") and g.get("category_id") != activity.get("category_id"):
            continue
        # Compute the date range for this goal period
        if g["period"] == "daily":
            start, end = today, today
        elif g["period"] == "weekly":
            start = start_of_week(today).date()
            end = end_of_week(today).date()
        else:  # monthly
            start = start_of_month(today).date()
            end = end_of_month(today).date()
        total = database.total_seconds_between(start.isoformat(), end.isoformat(),
                                                 g.get("category_id"))
        target = int(g["target_minutes"]) * 60
        if total >= target:
            _bump_streak(g, today)


def _bump_streak(goal: dict, today: _dt.date) -> None:
    """Bump (or initialize) the streak for a goal. Awards milestone badges."""
    from .i18n import t
    today_iso_str = today.isoformat()
    st = database.streak_for_goal(goal["id"])
    if not st:
        database.upsert_streak({
            "goal_id": goal["id"],
            "current": 1,
            "longest": 1,
            "last_hit_date": today_iso_str,
            "history": json.dumps([today_iso_str]),
        })
        # Award first-streak badge
        database.award_badge("first_streak", t("first_streak", "en"), t("first_streak", "fa"))
        return
    # Already hit today? Just update longest if needed.
    if st.get("last_hit_date") == today_iso_str:
        if st["current"] > st["longest"]:
            st["longest"] = st["current"]
            database.upsert_streak(st)
        return
    # Compute day delta from last hit
    last_iso = st.get("last_hit_date")
    if last_iso:
        try:
            last = _dt.date.fromisoformat(last_iso)
            delta = (today - last).days
        except ValueError:
            delta = -1
    else:
        delta = -1
    st["current"] = st["current"] + 1 if delta == 1 else 1
    if st["current"] > st["longest"]:
        st["longest"] = st["current"]
    st["last_hit_date"] = today_iso_str
    # Append to history (cap at 365 days)
    history = []
    try:
        history = json.loads(st.get("history") or "[]")
    except (json.JSONDecodeError, TypeError):
        history = []
    history.append(today_iso_str)
    if len(history) > 365:
        history = history[-365:]
    st["history"] = json.dumps(history)
    database.upsert_streak(st)
    # Award streak milestone badges (mirror timer.js)
    for threshold, key, en_title in config.STREAK_BADGES:
        if st["current"] == threshold:
            database.award_badge(key, en_title, t(key, "fa"))


# =====================================================================
# === MILESTONE BADGES (extends web edition) ===
# =====================================================================
def _check_milestone_badges() -> None:
    """Check and award activity-count milestone badges."""
    from .i18n import t
    count = database.count_activities()
    if count >= 1 and not database.has_badge("first_activity"):
        database.award_badge("first_activity",
                              t("first_activity", "en"), t("first_activity", "fa"))
    if count >= 10 and not database.has_badge("ten_activities"):
        database.award_badge("ten_activities",
                              t("ten_activities", "en"), t("ten_activities", "fa"))
    if count >= 100 and not database.has_badge("hundred_activities"):
        database.award_badge("hundred_activities",
                              t("hundred_activities", "en"), t("hundred_activities", "fa"))
    if count >= 1000 and not database.has_badge("thousand_activities"):
        database.award_badge("thousand_activities",
                              t("thousand_activities", "en"), t("thousand_activities", "fa"))
    # Check category diversity (explorer badge)
    cats_used = set()
    for a in database.recent_activities(500):
        if a.get("category_id"):
            cats_used.add(a["category_id"])
    if len(cats_used) >= 7 and not database.has_badge("explorer"):
        database.award_badge("explorer", t("explorer", "en"), t("explorer", "fa"))
    # Check for early bird (activity logged before 6 AM)
    now = _dt.datetime.now()
    if now.hour < 6 and not database.has_badge("early_bird"):
        database.award_badge("early_bird", t("early_bird", "en"), t("early_bird", "fa"))
    # Check for night owl (activity logged after midnight but before 4 AM)
    if 0 <= now.hour < 4 and not database.has_badge("night_owl"):
        database.award_badge("night_owl", t("night_owl", "en"), t("night_owl", "fa"))
    # Check for marathon (single activity > 4 hours)
    last = database.recent_activities(1)
    if last and int(last[0].get("duration_sec", 0)) >= 4 * 3600:
        if not database.has_badge("marathon"):
            database.award_badge("marathon", t("marathon", "en"), t("marathon", "fa"))


# =====================================================================
# === REMINDERS (desktop-only feature) ===
# =====================================================================
def check_reminders() -> None:
    """Check if any reminder should fire. Called periodically by app.py.
    
    For simplicity, this just checks if today's goal hasn't been met by the
    configured reminder hour, and is a no-op if there's no UI to show notifications.
    """
    if not is_running():
        # Optionally check if today's goal is met
        goals = database.all_goals(active_only=True)
        daily_goal = next((g for g in goals if g["period"] == "daily" and not g.get("category_id")), None)
        if daily_goal:
            target = int(daily_goal["target_minutes"]) * 60
            today_total = database.total_seconds_on(today_iso())
            if today_total < target:
                now = _dt.datetime.now()
                # Check if we're past the reminder time
                reminder_hour = config.REMINDER_DEFAULT_HOUR
                if now.hour >= reminder_hour and now.minute < 5:
                    # Could fire a desktop notification here
                    pass


# =====================================================================
# === DEBUG ===
# =====================================================================
def debug_state() -> dict:
    """Return the current timer state for debugging."""
    return _read_state()
