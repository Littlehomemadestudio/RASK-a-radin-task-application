"""
timer_service.py — Background stopwatch.

Cross-platform strategy:
  - On Android: tries to use python-for-android's foreground service to keep
    the stopwatch running while the app is backgrounded.
  - On desktop: runs a background thread.

The stopwatch itself is a wall-clock accumulator:
    elapsed = stored_elapsed + (now - last_start if running else 0)

This means we can survive process death by persisting (running, last_start,
elapsed, title, category_id) to the kv_store, and re-derive the live elapsed
on next app launch — no chronometer drift.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, Optional

from rask import config as cfg
from rask.data import database as db
from rask.utils import date_utils


KEY_RUNNING = "timer.running"
KEY_TITLE   = "timer.title"
KEY_CAT_ID  = "timer.category_id"
KEY_START   = "timer.last_start_unix"
KEY_ELAPSED = "timer.elapsed_sec"
KEY_TEMPLATE_ID = "timer.template_id"


_lock = threading.RLock()
_listeners: list[Callable[[int, bool], None]] = []
_tick_thread: Optional[threading.Thread] = None
_tick_stop = threading.Event()


# === State ===

def is_running() -> bool:
    return db.pref_get_bool(KEY_RUNNING, False)


def elapsed_sec() -> int:
    base = db.pref_get_int(KEY_ELAPSED, 0)
    if is_running():
        start = db.pref_get_int(KEY_START, 0)
        if start > 0:
            return base + int(time.time() - start)
    return base


def current_title() -> str:
    return db.pref_get(KEY_TITLE, "")


def current_category_id() -> Optional[int]:
    v = db.pref_get_int(KEY_CAT_ID, 0)
    return v or None


def current_template_id() -> Optional[int]:
    v = db.pref_get_int(KEY_TEMPLATE_ID, 0)
    return v or None


# === Control ===

def start(title: str, category_id: Optional[int] = None,
          template_id: Optional[int] = None) -> None:
    with _lock:
        if is_running():
            return
        now = int(time.time())
        db.pref_set(KEY_TITLE, title)
        db.pref_set_int(KEY_CAT_ID, category_id or 0)
        db.pref_set_int(KEY_TEMPLATE_ID, template_id or 0)
        db.pref_set_int(KEY_START, now)
        db.pref_set_bool(KEY_RUNNING, True)
    _notify_start_android()
    _start_ticker()


def pause() -> None:
    """Pause (not stop) — keeps accumulated time, can resume."""
    with _lock:
        if not is_running():
            return
        # commit elapsed
        e = elapsed_sec()
        db.pref_set_int(KEY_ELAPSED, e)
        db.pref_set_int(KEY_START, 0)
        db.pref_set_bool(KEY_RUNNING, False)
    _notify_stop_android()
    _emit(elapsed_sec(), False)


def resume() -> None:
    with _lock:
        if is_running():
            return
        db.pref_set_int(KEY_START, int(time.time()))
        db.pref_set_bool(KEY_RUNNING, True)
    _notify_start_android()
    _start_ticker()


def stop_and_save() -> Optional[int]:
    """Stop the timer and write a finished Activity row.

    Returns the new activity id, or None if nothing was running and no
    accumulated time existed.
    """
    from rask.data.models import Activity
    from rask.data.repositories import ActivityRepository

    with _lock:
        running = is_running()
        total = elapsed_sec()
        title = db.pref_get(KEY_TITLE, "")
        cat_id = current_category_id()
        tpl_id = current_template_id()

        # reset state
        db.pref_set_bool(KEY_RUNNING, False)
        db.pref_set_int(KEY_START, 0)
        db.pref_set_int(KEY_ELAPSED, 0)
        db.pref_set(KEY_TITLE, "")
        db.pref_set_int(KEY_CAT_ID, 0)
        db.pref_set_int(KEY_TEMPLATE_ID, 0)

    _notify_stop_android()

    if total < 5:
        return None  # ignore sub-5-second blips

    now = datetime.now()
    a = Activity(
        title=title or "(no title)",
        category_id=cat_id,
        kind=cfg.KIND_STOPWATCH,
        date_iso=now.date().isoformat(),
        start_iso=datetime.fromtimestamp(
            now.timestamp() - total
        ).isoformat(timespec="seconds"),
        end_iso=now.isoformat(timespec="seconds"),
        duration_sec=total,
        template_id=tpl_id,
    )
    aid = ActivityRepository.insert(a)
    _check_goals_after_save(a)
    return aid


def cancel() -> None:
    """Stop and discard without saving."""
    with _lock:
        db.pref_set_bool(KEY_RUNNING, False)
        db.pref_set_int(KEY_START, 0)
        db.pref_set_int(KEY_ELAPSED, 0)
        db.pref_set(KEY_TITLE, "")
        db.pref_set_int(KEY_CAT_ID, 0)
        db.pref_set_int(KEY_TEMPLATE_ID, 0)
    _notify_stop_android()
    _emit(0, False)


# === Listeners ===

def add_listener(cb: Callable[[int, bool], None]) -> None:
    _listeners.append(cb)


def remove_listener(cb: Callable[[int, bool], None]) -> None:
    if cb in _listeners:
        _listeners.remove(cb)


def _emit(elapsed: int, running: bool) -> None:
    for cb in list(_listeners):
        try:
            cb(elapsed, running)
        except Exception:
            pass


# === Ticker (in-process) ===

def _start_ticker() -> None:
    global _tick_thread
    if _tick_thread and _tick_thread.is_alive():
        return
    _tick_stop.clear()
    _tick_thread = threading.Thread(target=_tick_loop, daemon=True)
    _tick_thread.start()


def _tick_loop() -> None:
    while not _tick_stop.is_set():
        if not is_running():
            break
        _emit(elapsed_sec(), True)
        _tick_stop.wait(0.5)


# === Android foreground service ===

def _notify_start_android() -> None:
    try:
        from jnius import autoclass  # type: ignore
        # Start the foreground TimerService. The service class is defined
        # in java-src and registered in AndroidManifest via buildozer hooks.
        Intent = autoclass("android.content.Intent")
        Context = autoclass("org.kivy.android.PythonActivity")
        TimerService = autoclass("com.rask.TimerService")
        intent = Intent(Context.mActivity, TimerService)
        intent.putExtra("title", current_title())
        intent.putExtra("elapsed", int(elapsed_sec()))
        Context.mActivity.startService(intent)
    except Exception:
        pass  # Desktop or service unavailable


def _notify_stop_android() -> None:
    try:
        from jnius import autoclass  # type: ignore
        Intent = autoclass("android.content.Intent")
        Context = autoclass("org.kivy.android.PythonActivity")
        TimerService = autoclass("com.rask.TimerService")
        intent = Intent(Context.mActivity, TimerService)
        Context.mActivity.stopService(intent)
    except Exception:
        pass


# === Goal check ===

def _check_goals_after_save(activity) -> None:
    """After saving an activity, check daily/weekly goals and award streaks."""
    from rask.data.repositories import (
        GoalRepository, StreakRepository, BadgeRepository,
        ActivityRepository, CategoryRepository,
    )
    from rask.utils import date_utils as du

    today = du.iso_to_date(activity.date_iso)
    for goal in GoalRepository.all():
        if goal.category_id and goal.category_id != activity.category_id:
            continue
        if goal.period == cfg.PERIOD_DAILY:
            start = today
            end = today
        elif goal.period == cfg.PERIOD_WEEKLY:
            start = du.start_of_week(today)
            end = du.end_of_week(today)
        else:
            start = du.start_of_month(today)
            end = du.end_of_month(today)

        total_sec = ActivityRepository.total_seconds_between(
            start.isoformat(), end.isoformat(), goal.category_id
        )
        target_sec = goal.target_minutes * 60
        if total_sec >= target_sec:
            st = StreakRepository.for_goal(goal.id)
            if st is None:
                st = StreakRepository.upsert(
                    _new_streak(goal.id, today.isoformat())
                )
                st = StreakRepository.for_goal(goal.id)
            _bump_streak(st, today)


def _new_streak(goal_id, last_hit):
    from rask.data.models import Streak
    s = Streak(goal_id=goal_id, current=1, longest=1, last_hit_date=last_hit)
    StreakRepository.upsert(s)
    return s


def _bump_streak(streak, today_date) -> None:
    from datetime import date as _date
    from rask.data.repositories import StreakRepository
    last = streak.last_hit_date
    if last == today_date.isoformat():
        # already counted today
        if streak.current > streak.longest:
            streak.longest = streak.current
            StreakRepository.upsert(streak)
        return
    try:
        last_d = _date.fromisoformat(last) if last else None
    except ValueError:
        last_d = None
    if last_d and (today_date - last_d).days == 1:
        streak.current += 1
    else:
        streak.current = 1
    if streak.current > streak.longest:
        streak.longest = streak.current
    streak.last_hit_date = today_date.isoformat()
    StreakRepository.upsert(streak)

    # Award badges
    from rask.data.repositories import BadgeRepository
    if streak.current == 3:
        BadgeRepository.award("streak_3", "3-day streak", "۳ روز پیاپی")
    if streak.current == 7:
        BadgeRepository.award("streak_7", "7-day streak", "۷ روز پیاپی")
    if streak.current == 30:
        BadgeRepository.award("streak_30", "30-day streak", "۳۰ روز پیاپی")
    if streak.current == 100:
        BadgeRepository.award("streak_100", "100-day streak", "۱۰۰ روز پیاپی")
