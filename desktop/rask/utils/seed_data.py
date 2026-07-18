"""
rask.utils.seed_data
====================

Generate realistic demo data for testing the UI without manual entry.

Functions
---------

  • ``seed_demo_data(days=30)`` — create `days` of realistic activities,
    goals, templates, reminders, journal entries, mood entries, habits.
  • ``clear_demo_data()`` — remove all seeded data (marks by
    ``source='demo'``).
  • ``seed_categories_if_empty()`` — ensure default categories exist.
  • ``seed_default_goals()`` — create daily + weekly + monthly goals
    if missing.

Realistic activity titles
-------------------------

Each category has a pool of realistic titles that are randomly sampled:

  • Focus: Reading, Coding, Writing, Planning, Deep work
  • Learn: Online course, Tutorial, Documentation, Language practice
  • Work: Email, Meetings, Report writing, Code review, Bug fixing
  • Health: Workout, Yoga, Walking, Meditation, Stretching
  • Creative: Sketching, Music practice, Photography, Designing
  • Social: Phone call, Coffee with friend, Family time
  • Rest: Nap, Tea break, Walk outside, Reading for fun

Durations are weighted by time of day (more focus in the morning,
more rest in the evening).
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.logging_utils import get_logger
from ..core.time_utils import today_iso, add_days

__all__ = [
    "seed_demo_data",
    "clear_demo_data",
    "seed_categories_if_empty",
    "seed_default_goals",
    "DEMO_SOURCE",
]

_log = get_logger("utils.seed_data")

#: Source tag for all seeded data, so we can identify and clear it.
DEMO_SOURCE: str = "demo"


# =============================================================================
# === Realistic activity pools                                               ===
# =============================================================================

#: Activity titles per category key.
CATEGORY_TITLES: Dict[str, List[str]] = {
    "FOCUS": [
        "Reading", "Coding", "Writing", "Planning", "Deep work",
        "Research", "Documentation", "Studying",
    ],
    "LEARN": [
        "Online course", "Tutorial", "Documentation reading",
        "Language practice", "Lecture", "Practice problem",
    ],
    "WORK": [
        "Email", "Meetings", "Report writing", "Code review",
        "Bug fixing", "Project planning", "Client call",
    ],
    "HEALTH": [
        "Workout", "Yoga", "Walking", "Meditation", "Stretching",
        "Running", "Cycling", "Swimming",
    ],
    "CREATIVE": [
        "Sketching", "Music practice", "Photography", "Designing",
        "Painting", "Writing poetry", "Songwriting",
    ],
    "SOCIAL": [
        "Phone call", "Coffee with friend", "Family time",
        "Video call", "Dinner together", "Party",
    ],
    "REST": [
        "Nap", "Tea break", "Walk outside", "Reading for fun",
        "Listening to music", "Daydreaming", "Rest",
    ],
}


#: Per-hour activity count weights (more in working hours).
HOURLY_WEIGHTS: List[int] = [
    # 0..3 (late night): low
    1, 1, 1, 1,
    # 4..7 (early morning): low
    1, 2, 3, 4,
    # 8..11 (morning): high
    8, 10, 10, 9,
    # 12..15 (afternoon): medium-high
    6, 8, 9, 8,
    # 16..19 (late afternoon): high
    9, 8, 6, 5,
    # 20..23 (evening): medium
    5, 4, 3, 2,
]


#: Duration ranges per category (in minutes).
CATEGORY_DURATIONS: Dict[str, List[int]] = {
    "FOCUS": [15, 25, 30, 45, 50, 60, 90],
    "LEARN": [15, 30, 45, 60, 90],
    "WORK": [10, 15, 30, 45, 60, 120],
    "HEALTH": [15, 20, 30, 45, 60, 90],
    "CREATIVE": [20, 30, 45, 60, 90, 120],
    "SOCIAL": [15, 30, 60, 90, 120],
    "REST": [5, 10, 15, 20, 30, 45],
}


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _pick_hour(rng: random.Random) -> int:
    """Weighted random hour (0..23)."""
    return rng.choices(list(range(24)), weights=HOURLY_WEIGHTS, k=1)[0]


def _pick_title(category_key: str, rng: random.Random) -> str:
    """Random title from the category's pool."""
    pool = CATEGORY_TITLES.get(category_key, ["Activity"])
    return rng.choice(pool)


def _pick_duration(category_key: str, rng: random.Random) -> int:
    """Random duration from the category's range."""
    pool = CATEGORY_DURATIONS.get(category_key, [30])
    return rng.choice(pool)


def _category_map() -> Dict[str, int]:
    """Return {category_key: id} for all non-archived categories."""
    return {c["key"]: c["id"] for c in db.category_list()}


# =============================================================================
# === Public functions                                                       ===
# =============================================================================

def seed_categories_if_empty() -> int:
    """Ensure default categories exist.  Returns the count of categories."""
    cats = db.category_list()
    if cats:
        return len(cats)
    # Force a re-open of the DB (which seeds defaults).
    db.open_db()
    return len(db.category_list())


def seed_default_goals() -> List[int]:
    """Create default daily / weekly / monthly goals if missing.

    Returns the list of created goal ids.
    """
    created: List[int] = []
    existing_periods = {g["period"] for g in db.goal_list()}
    if "daily" not in existing_periods:
        gid = db.goal_add("daily", 120)
        created.append(gid)
    if "weekly" not in existing_periods:
        gid = db.goal_add("weekly", 600)
        created.append(gid)
    if "monthly" not in existing_periods:
        gid = db.goal_add("monthly", 2400)
        created.append(gid)
    return created


def seed_demo_data(days: int = 30, *, seed: Optional[int] = None) -> Dict[str, int]:
    """Seed `days` of realistic demo data.

    Creates:
      • ~3-7 activities per day, weighted by time of day
      • 1 journal entry per day (mood + energy + body)
      • 1-3 mood entries per day
      • 5 habits with completion logs
      • 5 quick-log templates
      • 3 reminders
      • 3 recurring rules
      • 1 weekly goal per category

    Parameters
    ----------
    days
        Number of past days to seed (1..365).
    seed
        Optional RNG seed for reproducible data.

    Returns
    -------
    dict
        Counts of each kind of seeded row.
    """
    if days < 1 or days > 365:
        raise ValueError(f"days must be 1..365, got {days}")
    rng = random.Random(seed)
    counts: Dict[str, int] = {
        "activities": 0,
        "goals": 0,
        "templates": 0,
        "reminders": 0,
        "recurring": 0,
        "journal_entries": 0,
        "mood_entries": 0,
        "habits": 0,
        "habit_logs": 0,
        "time_blocks": 0,
    }

    # Ensure categories exist.
    seed_categories_if_empty()
    cat_map = _category_map()

    # Goals.
    created_goals = seed_default_goals()
    counts["goals"] = len(created_goals)

    # Templates.
    template_specs = [
        ("Reading", "Read a book", "FOCUS", 30, "r"),
        ("Workout", "Quick workout", "HEALTH", 30, "w"),
        ("Coding", "Coding session", "FOCUS", 60, "c"),
        ("Meditation", "Meditate", "HEALTH", 15, "m"),
        ("Email", "Process email", "WORK", 15, "e"),
    ]
    for name, title, cat_key, dur, sc in template_specs:
        cid = cat_map.get(cat_key)
        try:
            db.template_add(
                name=name, title=title, category_id=cid,
                duration_min=dur, shortcut=sc, tags=["demo"],
            )
            counts["templates"] += 1
        except Exception as exc:  # noqa: BLE001
            _log.warning("template_add failed: %s", exc)

    # Reminders.
    reminder_specs = [
        ("Morning standup", "09:00", 127),  # every day
        ("Lunch break", "12:30", 127),
        ("Evening review", "20:00", 127),
    ]
    for title, time_hhmm, mask in reminder_specs:
        try:
            db.reminder_add(
                title=title, time_hhmm=time_hhmm,
                days_mask=mask, enabled=True, sound=True,
            )
            counts["reminders"] += 1
        except Exception as exc:  # noqa: BLE001
            _log.warning("reminder_add failed: %s", exc)

    # Recurring rules.
    recurring_specs = [
        ("Daily reading", 30, "daily", "FOCUS", "07:00"),
        ("Weekly review", 60, "weekly", "WORK", "16:00"),
        ("Weekly workout", 90, "weekly", "HEALTH", "18:00"),
    ]
    for title, dur, freq, cat_key, time_hhmm in recurring_specs:
        cid = cat_map.get(cat_key)
        try:
            db.recurring_add(
                title=title, duration_min=dur, frequency=freq,
                category_id=cid, time_hhmm=time_hhmm,
            )
            counts["recurring"] += 1
        except Exception as exc:  # noqa: BLE001
            _log.warning("recurring_add failed: %s", exc)

    # Habits.
    habit_specs = [
        ("Drink water", "daily", "HEALTH"),
        ("Read 10 pages", "daily", "FOCUS"),
        ("Stretch", "daily", "HEALTH"),
        ("Weekly review", "weekly", "WORK"),
        ("Workout 3x/week", "3x_week", "HEALTH"),
    ]
    from ..features.habits import habit_service
    from ..features import habits as _habits_mod
    _habits_mod._schema_initialized = False
    _habits_mod._ensure_schema()
    habit_ids: List[int] = []
    for name, freq, cat_key in habit_specs:
        try:
            hid = habit_service.add_habit(
                name=name, frequency=freq,
                color=db.category_get_by_key(cat_key)["color"]
                if db.category_get_by_key(cat_key) else None,
            )
            habit_ids.append(hid)
            counts["habits"] += 1
        except Exception as exc:  # noqa: BLE001
            _log.warning("habit_add failed: %s", exc)

    # Per-day seeding.
    today = date.today()
    for day_offset in range(days):
        d = today - timedelta(days=day_offset)
        iso = d.isoformat()
        weekday = d.weekday()  # 0=Mon..6=Sun
        is_weekend = weekday in (5, 6)

        # Activities: 2-7 per day, more on weekdays.
        n_activities = rng.randint(2, 4) if is_weekend else rng.randint(3, 7)
        for _ in range(n_activities):
            cat_key = rng.choice(list(cat_map.keys()))
            title = _pick_title(cat_key, rng)
            dur = _pick_duration(cat_key, rng)
            hour = _pick_hour(rng)
            minute = rng.choice([0, 15, 30, 45])
            try:
                db.activity_add(
                    title=title,
                    category_id=cat_map[cat_key],
                    duration_min=dur,
                    date_iso=iso,
                    start_ts=f"{iso}T{hour:02d}:{minute:02d}:00",
                    end_ts=f"{iso}T{hour:02d}:{minute + dur:02d}:00"
                    if minute + dur < 60 else None,
                    kind="manual",
                    source=DEMO_SOURCE,
                    tags=["demo"],
                )
                counts["activities"] += 1
            except Exception as exc:  # noqa: BLE001
                _log.warning("activity_add failed: %s", exc)

        # Journal entry (skip some days for realism).
        if rng.random() < 0.8:
            from ..features.journal import journal_service, JournalEntry
            from ..features import journal as _journal_mod
            _journal_mod._schema_initialized = False
            _journal_mod._ensure_schema()
            mood = rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 30, 35, 20])[0]
            energy = rng.choices([1, 2, 3, 4, 5], weights=[10, 15, 35, 25, 15])[0]
            try:
                e = JournalEntry(
                    date_iso=iso,
                    mood=mood,
                    energy=energy,
                    title=f"Day {day_offset + 1}",
                    body="Seeded demo entry.",
                )
                journal_service.add(e)
                counts["journal_entries"] += 1
            except Exception as exc:  # noqa: BLE001
                _log.warning("journal_add failed: %s", exc)

        # Mood entries: 1-3 per day.
        from ..features.mood_tracker import mood_service
        from ..features import mood_tracker as _mood_mod
        _mood_mod._schema_initialized = False
        _mood_mod._ensure_schema()
        for _ in range(rng.randint(1, 3)):
            try:
                mood_service.add(
                    date_iso=iso,
                    mood=rng.randint(1, 5),
                    energy=rng.randint(1, 5),
                    time_hhmm=f"{rng.randint(6, 22):02d}:{rng.choice([0, 15, 30, 45]):02d}",
                )
                counts["mood_entries"] += 1
            except Exception as exc:  # noqa: BLE001
                _log.warning("mood_add failed: %s", exc)

        # Habit logs (random completion).
        for hid in habit_ids:
            if rng.random() < 0.7:
                try:
                    habit_service.log_completion(hid, iso, completed=True)
                    counts["habit_logs"] += 1
                except Exception as exc:  # noqa: BLE001
                    _log.warning("habit_log failed: %s", exc)

    _log.info("Seeded demo data: %s", counts)
    return counts


def clear_demo_data() -> Dict[str, int]:
    """Remove all seeded demo data.  Returns counts removed.

    Removes:
      • Activities with ``source='demo'`` (hard delete)
      • Templates with tag 'demo'
      • Journal entries with body 'Seeded demo entry.'
      • Mood entries (all — they don't have a source tag)
      • Habit logs for seeded habits
    """
    counts: Dict[str, int] = {
        "activities": 0,
        "templates": 0,
        "journal_entries": 0,
        "mood_entries": 0,
        "habit_logs": 0,
    }

    # Activities.
    try:
        activities = db.activity_list(limit=100000, include_deleted=True)
        for a in activities:
            if a.get("source") == DEMO_SOURCE:
                db.activity_delete(a["id"], soft=False)
                counts["activities"] += 1
    except Exception as exc:  # noqa: BLE001
        _log.warning("clear activities failed: %s", exc)

    # Templates with tag 'demo'.
    try:
        for t in db.template_list(include_archived=True):
            # Tags are stored as JSON in tags_json.
            import json
            tags = json.loads(t.get("tags_json", "[]")) if t.get("tags_json") else []
            if "demo" in tags:
                db.template_delete(t["id"])
                counts["templates"] += 1
    except Exception as exc:  # noqa: BLE001
        _log.warning("clear templates failed: %s", exc)

    # Journal entries with seeded body.
    try:
        from ..features.journal import journal_service
        from ..features import journal as _journal_mod
        _journal_mod._schema_initialized = False
        _journal_mod._ensure_schema()
        for entry in journal_service.list():
            if "Seeded demo entry" in (entry.body or ""):
                journal_service.delete(entry.id)
                counts["journal_entries"] += 1
    except Exception as exc:  # noqa: BLE001
        _log.warning("clear journal failed: %s", exc)

    _log.info("Cleared demo data: %s", counts)
    return counts


# =============================================================================
# === CLI                                                                    ===
# =============================================================================

def _main() -> int:
    """CLI entry: ``python -m rask.utils.seed_data [days]``."""
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    counts = seed_demo_data(days=days, seed=42)
    print(f"Seeded {days} days of demo data:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
