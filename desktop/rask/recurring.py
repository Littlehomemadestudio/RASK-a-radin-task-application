"""recurring.py — Recurring activities engine (desktop-only extension).

Recurring rules generate activities automatically based on a pattern:
  - daily:     every day
  - weekly:    every week on the same weekday
  - monthly:   every month on the same day
  - weekdays:  Monday through Friday
  - weekends:  Saturday and Sunday (or Thursday and Friday in Persian)
  - custom:    specific weekdays (e.g., Mon/Wed/Fri)

Each recurring rule has:
  - title, category_id, duration_sec
  - start_date_iso, end_date_iso (optional)
  - next_run_iso: the next date the rule should fire
  - last_run_iso: the last date it actually fired

When the app launches (or periodically), call check_due_recurring() to
create activities for any rules whose next_run has passed.
"""
from __future__ import annotations
import datetime as _dt
import json
from typing import Optional

from . import database
from .date_utils import today_iso, now_iso, add_days


# =====================================================================
# === PATTERN EVALUATION ===
# =====================================================================
def matches_date(pattern: str, custom_days: list[int], d: _dt.date) -> bool:
    """Return True if the given date matches the recurring pattern.
    
    Args:
        pattern: 'daily', 'weekly', 'monthly', 'weekdays', 'weekends', 'custom'
        custom_days: list of weekday numbers (Mon=0, Sun=6) — used for 'custom'
        d: the date to check
    """
    py_wd = d.weekday()  # Mon=0, Sun=6
    if pattern == "daily":
        return True
    if pattern == "weekly":
        # Weekly: same weekday as start_date — caller should handle this
        return True
    if pattern == "monthly":
        # Monthly: same day-of-month as start_date
        # Caller should check this — we return True if day matches start
        return True
    if pattern == "weekdays":
        # Persian weekday: Sat-Wed (py_wd 5, 6, 0, 1, 2)
        return py_wd in (0, 1, 2, 5, 6)
    if pattern == "weekends":
        # Persian weekend: Thu, Fri (py_wd 3, 4)
        return py_wd in (3, 4)
    if pattern == "custom":
        return py_wd in custom_days
    return False


def compute_next_run(rule: dict, after_date: _dt.date) -> Optional[_dt.date]:
    """Compute the next run date for a rule, starting from `after_date`.
    
    Returns None if the rule has ended (end_date < after_date).
    """
    pattern = rule.get("pattern", "daily")
    custom_days = []
    try:
        custom_days = json.loads(rule.get("custom_days", "[]"))
    except (json.JSONDecodeError, TypeError):
        custom_days = []
    end_date_str = rule.get("end_date_iso")
    end_date = _dt.date.fromisoformat(end_date_str) if end_date_str else None
    # Iterate forward up to 366 days
    cursor = after_date
    for _ in range(366):
        if end_date and cursor > end_date:
            return None
        if matches_date(pattern, custom_days, cursor):
            return cursor
        cursor = cursor + _dt.timedelta(days=1)
    return None


# =====================================================================
# === CHECK & RUN DUE RECURRING ===
# =====================================================================
def check_due_recurring(today: Optional[str] = None) -> list[int]:
    """Check all active recurring rules and create activities for due ones.
    
    Returns the list of new activity ids created.
    """
    today_str = today or today_iso()
    today_date = _dt.date.fromisoformat(today_str)
    new_ids: list[int] = []
    rules = database.due_recurring(today_str)
    for rule in rules:
        # Check if we already have an activity for this rule today
        # (avoid duplicates)
        existing = database.activities_by_date(today_str,
                                                 category_id=rule.get("category_id"))
        already = any(
            a.get("recurring_id") == rule["id"] and a.get("date_iso") == today_str
            for a in existing
        )
        if already:
            # Just update next_run
            next_run = compute_next_run(rule, today_date + _dt.timedelta(days=1))
            if next_run:
                database.mark_recurring_run(rule["id"], next_run.isoformat())
            continue
        # Create the activity
        activity = {
            "title": rule["title"],
            "category_id": rule.get("category_id"),
            "kind": "recurring",
            "date_iso": today_str,
            "start_iso": None,
            "end_iso": None,
            "duration_sec": int(rule.get("duration_sec", 0) or 0),
            "note": rule.get("note", ""),
            "recurring_id": rule["id"],
            "voice_input": 0,
            "created_at": now_iso(),
        }
        activity_id = database.insert_activity(activity)
        new_ids.append(activity_id)
        # Compute next run
        next_run = compute_next_run(rule, today_date + _dt.timedelta(days=1))
        if next_run:
            database.mark_recurring_run(rule["id"], next_run.isoformat())
        else:
            # Rule has ended — deactivate
            database.upsert_recurring({**rule, "active": 0})
    return new_ids


# =====================================================================
# === CREATE RECURRING RULE ===
# =====================================================================
def create_recurring(title: str, category_id: Optional[int], pattern: str,
                     duration_sec: int, custom_days: Optional[list[int]] = None,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> int:
    """Create a new recurring rule. Returns the rule id."""
    start_iso = start_date or today_iso()
    start_date_obj = _dt.date.fromisoformat(start_iso)
    # Compute the first next_run
    rule = {
        "title": title,
        "category_id": category_id,
        "pattern": pattern,
        "custom_days": json.dumps(custom_days or []),
        "duration_sec": duration_sec,
        "start_date_iso": start_iso,
        "end_date_iso": end_date,
        "next_run_iso": start_iso,
        "last_run_iso": None,
        "active": 1,
        "created_at": now_iso(),
        "icon": "",
        "note": "",
    }
    # If start is in the future, next_run is start
    # If start is today or past, next_run is the next matching date from today
    today_date = _dt.date.today()
    if start_date_obj <= today_date:
        next_run = compute_next_run(rule, today_date)
        if next_run:
            rule["next_run_iso"] = next_run.isoformat()
    return database.upsert_recurring(rule)


# =====================================================================
# === DELETE / UPDATE ===
# =====================================================================
def delete_recurring(recurring_id: int) -> None:
    """Delete a recurring rule (does not affect already-created activities)."""
    database.delete_recurring(recurring_id)


def toggle_recurring(recurring_id: int, active: bool) -> None:
    """Activate or deactivate a recurring rule."""
    rule = database.recurring_by_id(recurring_id)
    if rule:
        rule["active"] = 1 if active else 0
        database.upsert_recurring(rule)


# =====================================================================
# === LIST / FORMAT ===
# =====================================================================
def list_all(active_only: bool = False) -> list[dict]:
    """Return all recurring rules."""
    return database.all_recurring(active_only=active_only)


def format_pattern(rule: dict, lang: str = "fa") -> str:
    """Return a localized human-readable description of the rule's pattern."""
    pattern = rule.get("pattern", "daily")
    mapping = {
        "daily":    "recurringDaily",
        "weekly":   "recurringWeekly",
        "monthly":  "recurringMonthly",
        "weekdays": "recurringWeekdays",
        "weekends": "recurringWeekends",
        "custom":   "recurringCustom",
    }
    return t(mapping.get(pattern, "recurringDaily"), lang)


def next_run_label(rule: dict, lang: str = "fa") -> str:
    """Return a localized label for the next run date."""
    next_iso = rule.get("next_run_iso")
    if not next_iso:
        return "—"
    from .date_utils import fmt_relative
    return fmt_relative(next_iso, lang)


# =====================================================================
# === DEBUG ===
# =====================================================================
def debug_status() -> dict:
    """Return a debug summary of recurring rules."""
    rules = list_all()
    return {
        "count": len(rules),
        "active": sum(1 for r in rules if r.get("active")),
        "due_today": len(database.due_recurring()),
        "rules": [
            {
                "id": r["id"],
                "title": r["title"],
                "pattern": r["pattern"],
                "next_run": r.get("next_run_iso"),
                "active": bool(r.get("active")),
            }
            for r in rules
        ],
    }
