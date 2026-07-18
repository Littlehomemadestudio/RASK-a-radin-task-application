"""timer_service.py — Background stopwatch with persistence (mirror of web/js/timer.js).

State is persisted in the kv table as JSON (key 'timer_state'):
    {running, title, category_id, template_id, start_ts_ms, elapsed_sec}
Tick: a background thread emits updates to listeners every 1 second while running.
On stop&save: inserts an activity, then evaluates goals → bumps streaks → awards badges.
"""
from __future__ import annotations
import datetime as _dt
import threading
import time
from typing import Callable, List, Optional
from . import config
from . import database
from .date_utils import (
    now_iso, today_iso, start_of_week, end_of_week,
    start_of_month, end_of_month,
)


_TIMER_KEY = "timer_state"
_lock = threading.RLock()
_listeners: List[Callable[[int, bool], None]] = []
_tick_thread: Optional[threading.Thread] = None
_tick_stop = threading.Event()


def _read() -> dict:
    raw = database.kv_get(_TIMER_KEY, None)
    if not raw:
        return {}
    try:
        import json
        return json.loads(raw)
    except Exception:
        return {}


def _write(state: dict) -> None:
    import json
    database.kv_set(_TIMER_KEY, json.dumps(state))


def is_running() -> bool:
    return bool(_read().get("running"))


def elapsed_sec() -> int:
    s = _read()
    if not s:
        return 0
    e = int(s.get("elapsed", 0) or 0)
    if s.get("running") and s.get("start_ts"):
        e += int((time.time() * 1000 - s["start_ts"]) / 1000)
    return e


def current_title() -> str:
    return _read().get("title", "")


def current_category_id():
    return _read().get("category_id")


def current_template_id():
    return _read().get("template_id")


def start(title: str, category_id: Optional[int], template_id: Optional[int]) -> None:
    with _lock:
        if is_running():
            return
        prev = _read()
        _write({
            "running": True,
            "title": title or "",
            "category_id": category_id,
            "template_id": template_id,
            "start_ts": int(time.time() * 1000),
            "elapsed": int(prev.get("elapsed", 0) or 0),
        })
        _start_tick()
        _emit()


def pause() -> None:
    with _lock:
        if not is_running():
            return
        s = _read()
        s["running"] = False
        s["start_ts"] = None
        s["elapsed"] = elapsed_sec()
        _write(s)
        _emit()


def resume() -> None:
    with _lock:
        if is_running():
            return
        s = _read()
        s["running"] = True
        s["start_ts"] = int(time.time() * 1000)
        _write(s)
        _start_tick()
        _emit()


def stop_and_save() -> Optional[int]:
    """Stop the timer and persist the activity. Returns new activity id (or None if <5s)."""
    with _lock:
        s = _read()
        total = elapsed_sec()
        _write({})
        _emit()

    if total < 5:
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
        "created_at": now_iso(),
    }
    aid = database.insert_activity(activity)
    _check_goals_after_save(activity)
    return aid


def cancel() -> None:
    with _lock:
        _write({})
        _emit()


# === Listeners ===
def add_listener(cb: Callable[[int, bool], None]) -> None:
    with _lock:
        _listeners.append(cb)


def remove_listener(cb: Callable[[int, bool], None]) -> None:
    with _lock:
        _listeners[:] = [x for x in _listeners if x is not cb]


def _emit() -> None:
    e = elapsed_sec()
    r = is_running()
    for cb in list(_listeners):
        try:
            cb(e, r)
        except Exception:
            pass


def _start_tick() -> None:
    global _tick_thread
    if _tick_thread and _tick_thread.is_alive():
        return
    _tick_stop.clear()
    _tick_thread = threading.Thread(target=_tick_loop, daemon=True)
    _tick_thread.start()


def _tick_loop() -> None:
    while not _tick_stop.is_set():
        if not is_running():
            return
        _emit()
        _tick_stop.wait(1.0)


# === Goal & streak checking (mirror of timer.js checkGoalsAfterSave / bumpStreak) ===
def _check_goals_after_save(activity: dict) -> None:
    goals = database.all_goals(active_only=True)
    today = _dt.datetime.strptime(activity["date_iso"], "%Y-%m-%d")
    for g in goals:
        if g["category_id"] and g["category_id"] != activity.get("category_id"):
            continue
        if g["period"] == "daily":
            start, end = today, today
        elif g["period"] == "weekly":
            start, end = start_of_week(today), end_of_week(today)
        else:
            start, end = start_of_month(today), end_of_month(today)
        total = database.total_seconds_between(
            start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), g["category_id"]
        )
        target = g["target_minutes"] * 60
        if total >= target:
            _bump_streak(g, today)


def _bump_streak(goal: dict, today: _dt.datetime) -> None:
    st = database.streak_for_goal(goal["id"])
    today_iso_str = today.strftime("%Y-%m-%d")
    if not st:
        database.upsert_streak({
            "goal_id": goal["id"], "current": 1, "longest": 1,
            "last_hit_date": today_iso_str,
        })
        return
    if st["last_hit_date"] == today_iso_str:
        if st["current"] > st["longest"]:
            st["longest"] = st["current"]
            database.upsert_streak(st)
        return
    last = None
    if st.get("last_hit_date"):
        last = _dt.datetime.strptime(st["last_hit_date"], "%Y-%m-%d")
    diff = (today - last).days if last else -1
    st["current"] = st["current"] + 1 if diff == 1 else 1
    if st["current"] > st["longest"]:
        st["longest"] = st["current"]
    st["last_hit_date"] = today_iso_str
    database.upsert_streak(st)
    # Award badges (mirror of timer.js bumpStreak)
    from .i18n import t
    cur_lang = database.kv_get("lang", "fa") or "fa"
    for milestone, key, title_en in config.STREAK_BADGES:
        if st["current"] == milestone:
            database.award_badge(key, title_en, t(f"streak{milestone}", cur_lang))


def init_on_startup() -> None:
    """If the timer was running when the app closed, resume ticking."""
    if is_running():
        _start_tick()
