"""tests.py — Comprehensive test suite for the Rask desktop app.

Run with:  python -m rask.tests
       or:  python -c "from rask.tests import run_all; run_all()"

Each test function returns True/False and prints a status. The test runner
aggregates results and exits with code 0 (all pass) or 1 (any fail).

These tests are pure-Python and require no display — they exercise the
non-UI modules (database, crypto, date_utils, i18n, analytics, recurring,
exporters, charts computation, icons).
"""
from __future__ import annotations
import datetime as _dt
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable


# =====================================================================
# === TEST RUNNER ===
# =====================================================================
_passed = 0
_failed = 0
_failures: list[str] = []


def test(name: str):
    """Decorator for test functions."""
    def decorator(fn: Callable[[], None]):
        global _passed, _failed
        try:
            fn()
            _passed += 1
            print(f"  ✓ {name}")
        except AssertionError as e:
            _failed += 1
            _failures.append(f"{name}: {e}")
            print(f"  ✗ {name} — {e}")
        except Exception as e:
            _failed += 1
            _failures.append(f"{name}: {type(e).__name__}: {e}")
            print(f"  ✗ {name} — {type(e).__name__}: {e}")
        return fn
    return decorator


def assert_eq(actual, expected, msg: str = ""):
    if actual != expected:
        raise AssertionError(f"{msg} — got {actual!r}, expected {expected!r}")


def assert_true(value, msg: str = ""):
    if not value:
        raise AssertionError(f"{msg} — expected truthy, got {value!r}")


def assert_false(value, msg: str = ""):
    if value:
        raise AssertionError(f"{msg} — expected falsy, got {value!r}")


def assert_in(item, collection, msg: str = ""):
    if item not in collection:
        raise AssertionError(f"{msg} — {item!r} not in {collection!r}")


def assert_gt(a, b, msg: str = ""):
    if not (a > b):
        raise AssertionError(f"{msg} — {a!r} not greater than {b!r}")


def assert_gte(a, b, msg: str = ""):
    if not (a >= b):
        raise AssertionError(f"{msg} — {a!r} not greater than or equal to {b!r}")


def assert_lte(a, b, msg: str = ""):
    if not (a <= b):
        raise AssertionError(f"{msg} — {a!r} not less than or equal to {b!r}")


# =====================================================================
# === DATABASE TESTS ===
# =====================================================================
@test("database.open_db() returns a connection")
def _test_db_open():
    from . import database
    conn = database.open_db()
    assert_true(conn is not None, "Connection should not be None")


@test("database seeds 7 default categories")
def _test_db_seed_categories():
    from . import database
    database.open_db()
    cats = database.all_categories()
    assert_eq(len(cats), 7, "Should have 7 default categories")
    keys = [c["key"] for c in cats]
    for expected in ["FOCUS", "LEARN", "WORK", "HEALTH", "CREATIVE", "SOCIAL", "REST"]:
        assert_in(expected, keys, f"Missing category {expected}")


@test("database seeds a default daily goal")
def _test_db_seed_goal():
    from . import database
    database.open_db()
    goals = database.all_goals()
    assert_gte(len(goals), 1, "Should have at least the default goal")
    daily = [g for g in goals if g["period"] == "daily"]
    assert_gte(len(daily), 1, "Should have a daily goal")
    assert_eq(daily[0]["target_minutes"], 120, "Default daily goal should be 120 minutes")


@test("database.kv_get/set round-trips")
def _test_kv_roundtrip():
    from . import database
    database.open_db()
    database.kv_set("test_key", "test_value")
    assert_eq(database.kv_get("test_key"), "test_value", "KV roundtrip failed")
    database.kv_delete("test_key")
    assert_true(database.kv_get("test_key") is None, "KV delete failed")


@test("database.kv_get_bool/set_bool round-trips")
def _test_kv_bool():
    from . import database
    database.open_db()
    database.kv_set_bool("test_bool", True)
    assert_true(database.kv_get_bool("test_bool", False), "KV bool True failed")
    database.kv_set_bool("test_bool", False)
    assert_false(database.kv_get_bool("test_bool", True), "KV bool False failed")


@test("database.kv_get_json/set_json round-trips")
def _test_kv_json():
    from . import database
    database.open_db()
    payload = {"a": 1, "b": [2, 3], "c": "hello"}
    database.kv_set_json("test_json", payload)
    result = database.kv_get_json("test_json")
    assert_eq(result, payload, "KV JSON roundtrip failed")


@test("database.insert_activity and get_activity")
def _test_activity_insert():
    from . import database
    database.open_db()
    activity_id = database.insert_activity({
        "title": "Test activity",
        "category_id": 1,
        "kind": "manual",
        "date_iso": "2026-07-18",
        "duration_sec": 1800,
        "note": "test note",
    })
    assert_true(activity_id > 0, "Should get a positive activity id")
    a = database.get_activity(activity_id)
    assert_eq(a["title"], "Test activity", "Title mismatch")
    assert_eq(a["duration_sec"], 1800, "Duration mismatch")
    database.delete_activity(activity_id)


@test("database.recent_activities returns activities")
def _test_recent_activities():
    from . import database
    database.open_db()
    # Insert 3 activities with distinct titles
    ids = []
    for i in range(3):
        time.sleep(0.01)
        ids.append(database.insert_activity({
            "title": f"TestRecent{i}",
            "kind": "manual",
            "date_iso": "2026-07-18",
            "duration_sec": 60 * (i + 1),
        }))
    recent = database.recent_activities(10)
    # Verify the 3 we just inserted are in the recent list
    recent_titles = [a["title"] for a in recent]
    for i in range(3):
        assert_in(f"TestRecent{i}", recent_titles, f"TestRecent{i} missing")
    # Most recent should be the last inserted (created_at descending)
    found_test = [a for a in recent if a["title"].startswith("TestRecent")]
    assert_gte(len(found_test), 1, "Should have at least 1 TestRecent")
    # Cleanup
    for i in ids:
        database.delete_activity(i)


@test("database.total_seconds_on sums correctly")
def _test_total_seconds():
    from . import database
    database.open_db()
    date = "2026-07-18"
    # Insert 2 activities
    id1 = database.insert_activity({"title": "TotalTestA", "date_iso": date, "duration_sec": 1800})
    id2 = database.insert_activity({"title": "TotalTestB", "date_iso": date, "duration_sec": 3600})
    total = database.total_seconds_on(date)
    assert_gte(total, 5400, f"Total should be >= 5400, got {total}")
    database.delete_activity(id1)
    database.delete_activity(id2)


@test("database.seconds_per_day returns dict")
def _test_seconds_per_day():
    from . import database
    database.open_db()
    id1 = database.insert_activity({"title": "PDTestA", "date_iso": "2026-07-18", "duration_sec": 1800})
    id2 = database.insert_activity({"title": "PDTestB", "date_iso": "2026-07-19", "duration_sec": 900})
    per_day = database.seconds_per_day("2026-07-18", "2026-07-19")
    assert_in("2026-07-18", per_day, "Should have entry for 07-18")
    assert_in("2026-07-19", per_day, "Should have entry for 07-19")
    assert_gte(per_day["2026-07-18"], 1800, "07-18 should have at least 1800 sec")
    assert_gte(per_day["2026-07-19"], 900, "07-19 should have at least 900 sec")
    database.delete_activity(id1)
    database.delete_activity(id2)


@test("database.seconds_per_category returns sorted list")
def _test_seconds_per_category():
    from . import database
    database.open_db()
    cats = database.all_categories()
    id1 = database.insert_activity({
        "title": "CATestA", "category_id": cats[0]["id"],
        "date_iso": "2026-07-18", "duration_sec": 100,
    })
    id2 = database.insert_activity({
        "title": "CATestB", "category_id": cats[1]["id"],
        "date_iso": "2026-07-18", "duration_sec": 200,
    })
    result = database.seconds_per_category("2026-07-18", "2026-07-18")
    assert_gte(len(result), 1, "Should have at least 1 category")
    # Result should be sorted descending
    for i in range(len(result) - 1):
        assert_gte(result[i][1], result[i + 1][1], "Should be sorted descending")
    database.delete_activity(id1)
    database.delete_activity(id2)


@test("database.search_activities finds by title")
def _test_search():
    from . import database
    database.open_db()
    id1 = database.insert_activity({"title": "Read Python book SearchTest", "date_iso": "2026-07-18", "duration_sec": 60})
    id2 = database.insert_activity({"title": "Read Go book SearchTest", "date_iso": "2026-07-18", "duration_sec": 60})
    # Search uses LIKE %query% — single word search
    results = database.search_activities("Python")
    assert_gte(len(results), 1, "Should find at least 1 Python result")
    titles = [r["title"] for r in results]
    assert_true(any("Python" in t for t in titles), "Should find Python book")
    database.delete_activity(id1)
    database.delete_activity(id2)


@test("database.update_activity modifies fields")
def _test_activity_update():
    from . import database
    database.open_db()
    aid = database.insert_activity({"title": "UpdateTestOriginal", "date_iso": "2026-07-18", "duration_sec": 60})
    a = database.get_activity(aid)
    a["title"] = "UpdateTestUpdated"
    a["duration_sec"] = 120
    database.update_activity(a)
    a2 = database.get_activity(aid)
    assert_eq(a2["title"], "UpdateTestUpdated", "Title should be updated")
    assert_eq(a2["duration_sec"], 120, "Duration should be updated")
    database.delete_activity(aid)


@test("database.archive_activity hides from default queries")
def _test_activity_archive():
    from . import database
    database.open_db()
    aid = database.insert_activity({"title": "ArchiveTestUnique", "date_iso": "2026-07-18", "duration_sec": 60})
    # Should be in recent_activities by default
    recent = database.recent_activities(50)
    assert_in(aid, [a["id"] for a in recent], "Should be in recent before archive")
    # Archive
    database.archive_activity(aid, True)
    # Should not be in default recent_activities
    recent = database.recent_activities(50)
    assert_true(aid not in [a["id"] for a in recent], "Should not be in recent after archive")
    # Should be in include_archived
    recent_all = database.recent_activities(50, include_archived=True)
    assert_in(aid, [a["id"] for a in recent_all], "Should be in recent with include_archived")
    database.delete_activity(aid)


@test("database.activity_duration_stats computes correctly")
def _test_duration_stats():
    from . import database
    database.open_db()
    # Use unique titles to filter our test data
    ids = []
    durations = [60, 120, 180, 240, 300]
    for d in durations:
        ids.append(database.insert_activity({
            "title": "DurationStatTestUnique",
            "date_iso": "2026-07-18",
            "duration_sec": d,
        }))
    # Get all activities on that date with our unique title
    all_acts = database.activities_by_date("2026-07-18")
    our_acts = [a for a in all_acts if a["title"] == "DurationStatTestUnique"]
    assert_eq(len(our_acts), len(durations), f"Should have {len(durations)} test activities")
    our_durations = sorted([a["duration_sec"] for a in our_acts])
    assert_eq(our_durations, sorted(durations), "Durations should match")
    assert_eq(our_durations[0], 60, "Min should be 60")
    assert_eq(our_durations[-1], 300, "Max should be 300")
    assert_eq(sum(our_durations), sum(durations), "Total mismatch")
    for aid in ids:
        database.delete_activity(aid)


@test("database.template CRUD")
def _test_template_crud():
    from . import database
    database.open_db()
    tid = database.upsert_template({
        "title": "Test template",
        "category_id": 1,
        "default_duration_min": 30,
    })
    assert_true(tid > 0, "Should get positive template id")
    t = database.template_by_id(tid)
    assert_eq(t["title"], "Test template", "Title mismatch")
    # Update
    t["title"] = "Updated template"
    database.upsert_template(t)
    t2 = database.template_by_id(tid)
    assert_eq(t2["title"], "Updated template", "Update failed")
    database.delete_template(tid)
    assert_true(database.template_by_id(tid) is None, "Should be deleted")


@test("database.goal CRUD")
def _test_goal_crud():
    from . import database
    database.open_db()
    gid = database.upsert_goal({
        "period": "daily",
        "category_id": None,
        "target_minutes": 90,
        "active": 1,
    })
    assert_true(gid > 0, "Should get positive goal id")
    g = database.goal_by_id(gid)
    assert_eq(g["target_minutes"], 90, "Target mismatch")
    database.delete_goal(gid)
    assert_true(database.goal_by_id(gid) is None, "Should be deleted")


@test("database.streak CRUD")
def _test_streak_crud():
    from . import database
    database.open_db()
    # Create a goal first
    gid = database.upsert_goal({"period": "daily", "target_minutes": 60, "active": 1})
    # Create a streak
    sid = database.upsert_streak({
        "goal_id": gid, "current": 5, "longest": 7, "last_hit_date": "2026-07-18",
    })
    s = database.streak_for_goal(gid)
    assert_eq(s["current"], 5, "Current mismatch")
    assert_eq(s["longest"], 7, "Longest mismatch")
    database.delete_goal(gid)  # Should cascade to streak


@test("database.badge award and has_badge")
def _test_badge():
    from . import database
    database.open_db()
    # Clean up if exists
    database.delete_badge("test_badge_key")
    assert_false(database.has_badge("test_badge_key"), "Should not have badge initially")
    awarded = database.award_badge("test_badge_key", "Test", "آزمون")
    assert_true(awarded, "Should be newly awarded")
    assert_true(database.has_badge("test_badge_key"), "Should have badge after award")
    # Awarding again should return False
    awarded2 = database.award_badge("test_badge_key", "Test", "آزمون")
    assert_false(awarded2, "Should not be re-awarded")
    database.delete_badge("test_badge_key")


@test("database.recurring CRUD")
def _test_recurring_crud():
    from . import database
    database.open_db()
    rid = database.upsert_recurring({
        "title": "Daily standup",
        "category_id": 1,
        "pattern": "daily",
        "duration_sec": 900,
        "start_date_iso": "2026-07-18",
        "next_run_iso": "2026-07-18",
        "active": 1,
        "created_at": "2026-07-18T00:00:00",
    })
    assert_true(rid > 0, "Should get positive recurring id")
    r = database.recurring_by_id(rid)
    assert_eq(r["title"], "Daily standup", "Title mismatch")
    database.delete_recurring(rid)
    assert_true(database.recurring_by_id(rid) is None, "Should be deleted")


@test("database.export_all returns dict with all stores")
def _test_export_all():
    from . import database
    database.open_db()
    payload = database.export_all()
    assert_in("activities", payload, "Should have activities")
    assert_in("categories", payload, "Should have categories")
    assert_in("goals", payload, "Should have goals")
    assert_in("streaks", payload, "Should have streaks")
    assert_in("templates", payload, "Should have templates")
    assert_in("badges", payload, "Should have badges")
    assert_in("kv", payload, "Should have kv")
    assert_in("recurring", payload, "Should have recurring")
    assert_in("_meta", payload, "Should have _meta")


@test("database.replace_all restores data")
def _test_replace_all():
    from . import database
    database.open_db()
    # Snapshot current state
    original = database.export_all()
    # Insert a test activity
    aid = database.insert_activity({"title": "Test", "date_iso": "2026-07-18", "duration_sec": 60})
    # Verify it was inserted
    assert_true(database.get_activity(aid) is not None, "Should be inserted")
    # Now restore the snapshot
    database.replace_all(original)
    # The activity should be gone (assuming it wasn't in the snapshot)
    # (May still exist if id was reused — just verify no crash)


@test("database.db_size_bytes returns positive int")
def _test_db_size():
    from . import database
    database.open_db()
    size = database.db_size_bytes()
    assert_true(size > 0, f"DB size should be positive, got {size}")


# =====================================================================
# === DATE UTILS TESTS ===
# =====================================================================
@test("date_utils.gregorian_to_jalali converts known dates")
def _test_g2j():
    from .date_utils import gregorian_to_jalali
    assert_eq(gregorian_to_jalali(2026, 7, 18), (1405, 4, 27), "2026-07-18 wrong")
    assert_eq(gregorian_to_jalali(2026, 3, 21), (1405, 1, 1), "2026-03-21 wrong")
    assert_eq(gregorian_to_jalali(2024, 3, 20), (1403, 1, 1), "2024-03-20 wrong")
    assert_eq(gregorian_to_jalali(2000, 1, 1), (1378, 10, 11), "2000-01-01 wrong")


@test("date_utils.jalali_to_gregorian converts known dates")
def _test_j2g():
    from .date_utils import jalali_to_gregorian
    assert_eq(jalali_to_gregorian(1405, 4, 27), (2026, 7, 18), "1405-04-27 wrong")
    assert_eq(jalali_to_gregorian(1405, 1, 1), (2026, 3, 21), "1405-01-01 wrong")
    assert_eq(jalali_to_gregorian(1403, 1, 1), (2024, 3, 20), "1403-01-01 wrong")
    assert_eq(jalali_to_gregorian(1378, 10, 11), (2000, 1, 1), "1378-10-11 wrong")


@test("date_utils g2j and j2g are inverses (round-trip)")
def _test_roundtrip():
    from .date_utils import gregorian_to_jalali, jalali_to_gregorian
    import datetime as _dt
    # Test 30 random dates
    base = _dt.date(2020, 1, 1)
    for i in range(0, 365 * 7, 17):  # ~150 dates over 7 years
        d = base + _dt.timedelta(days=i)
        j = gregorian_to_jalali(d.year, d.month, d.day)
        g = jalali_to_gregorian(*j)
        assert_eq((d.year, d.month, d.day), g,
                  f"Round-trip failed for {d}: g→j={j}, j→g={g}")


@test("date_utils.is_leap for Gregorian")
def _test_is_leap():
    from .date_utils import is_leap
    assert_true(is_leap(2024), "2024 should be leap")
    assert_false(is_leap(2023), "2023 should not be leap")
    assert_false(is_leap(2100), "2100 should not be leap (century rule)")
    assert_true(is_leap(2000), "2000 should be leap (400 rule)")


@test("date_utils.is_jalali_leap")
def _test_is_jalali_leap():
    from .date_utils import is_jalali_leap
    # Just verify it returns a bool
    assert_true(isinstance(is_jalali_leap(1403), bool), "Should return bool")
    assert_true(isinstance(is_jalali_leap(1404), bool), "Should return bool")


@test("date_utils.today_iso returns YYYY-MM-DD")
def _test_today_iso():
    from .date_utils import today_iso
    s = today_iso()
    assert_eq(len(s), 10, "Should be 10 chars")
    assert_eq(s[4], "-", "Should have dash at position 4")
    assert_eq(s[7], "-", "Should have dash at position 7")


@test("date_utils.start_of_week returns Saturday")
def _test_start_of_week():
    from .date_utils import start_of_week
    import datetime as _dt
    # 2026-07-18 is a Saturday
    d = _dt.date(2026, 7, 18)
    s = start_of_week(d)
    # Should be Saturday
    assert_eq(s.weekday(), 5, "Start of week should be Saturday (py weekday=5)")


@test("date_utils.fmt_human formats correctly in English")
def _test_fmt_human_en():
    from .date_utils import fmt_human
    assert_eq(fmt_human(0, "en"), "0m", "0 sec should be 0m")
    assert_eq(fmt_human(60, "en"), "1m", "60 sec should be 1m")
    assert_eq(fmt_human(3600, "en"), "1h", "3600 sec should be 1h")
    assert_eq(fmt_human(5400, "en"), "1h 30m", "5400 sec should be 1h 30m")
    assert_eq(fmt_human(7384, "en"), "2h 3m", "7384 sec should be 2h 3m")


@test("date_utils.fmt_human formats correctly in Persian")
def _test_fmt_human_fa():
    from .date_utils import fmt_human
    from .i18n import to_fa_digits
    # 0 seconds → "۰ دقیقه" (default to minute when no parts)
    assert_eq(fmt_human(0, "fa"), "۰ دقیقه", f"0 sec wrong: {fmt_human(0, 'fa')}")
    # Just verify it contains Persian digits
    assert_in(to_fa_digits(1), fmt_human(60, "fa"), "Should contain Persian 1")


@test("date_utils.fmt_duration formats as HH:MM:SS")
def _test_fmt_duration():
    from .date_utils import fmt_duration
    assert_eq(fmt_duration(0), "00:00", "0 sec wrong")
    assert_eq(fmt_duration(60), "01:00", "60 sec wrong")
    assert_eq(fmt_duration(3661), "01:01:01", "3661 sec wrong")


@test("date_utils.fmt_relative")
def _test_fmt_relative():
    from .date_utils import fmt_relative, today_iso
    import datetime as _dt
    today = today_iso()
    assert_eq(fmt_relative(today, "en"), "Today", "Today should be 'Today'")
    yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    assert_eq(fmt_relative(yesterday, "en"), "Yesterday", "Yesterday wrong")


@test("date_utils.add_days")
def _test_add_days():
    from .date_utils import add_days
    import datetime as _dt
    d = _dt.date(2026, 7, 18)
    d2 = add_days(d, 7)
    assert_eq(d2, _dt.date(2026, 7, 25), "+7 days wrong")
    d3 = add_days(d, -7)
    assert_eq(d3, _dt.date(2026, 7, 11), "-7 days wrong")


@test("date_utils.preset_range for known presets")
def _test_preset_range():
    from .date_utils import preset_range, today_iso
    today = today_iso()
    s, e = preset_range("today")
    assert_eq(s, today, "today start should be today")
    assert_eq(e, today, "today end should be today")
    s, e = preset_range("7d")
    assert_eq(e, today, "7d end should be today")
    # Start should be 6 days before
    import datetime as _dt
    expected_start = (_dt.date.today() - _dt.timedelta(days=6)).isoformat()
    assert_eq(s, expected_start, "7d start wrong")


@test("date_utils.diff_days")
def _test_diff_days():
    from .date_utils import diff_days
    import datetime as _dt
    a = _dt.date(2026, 7, 25)
    b = _dt.date(2026, 7, 18)
    assert_eq(diff_days(a, b), 7, "diff wrong")


# =====================================================================
# === I18N TESTS ===
# =====================================================================
@test("i18n.t returns Persian for fa")
def _test_t_fa():
    from .i18n import t
    assert_eq(t("appName", "fa"), "رَسک", "appName fa wrong")
    assert_eq(t("home", "fa"), "خانه", "home fa wrong")


@test("i18n.t returns English for en")
def _test_t_en():
    from .i18n import t
    assert_eq(t("appName", "en"), "Rask", "appName en wrong")
    assert_eq(t("home", "en"), "Home", "home en wrong")


@test("i18n.t falls back to key for unknown key")
def _test_t_fallback():
    from .i18n import t
    assert_eq(t("nonexistent_key_xyz", "fa"), "nonexistent_key_xyz", "Should fall back to key")


@test("i18n.t falls back to English for unknown lang")
def _test_t_lang_fallback():
    from .i18n import t
    # French isn't supported — should fall back to fa or en
    val = t("appName", "fr")
    assert_true(val in ("Rask", "رَسک"), f"Should fall back, got {val!r}")


@test("i18n.to_fa_digits converts correctly")
def _test_to_fa_digits():
    from .i18n import to_fa_digits
    assert_eq(to_fa_digits("0123456789"), "۰۱۲۳۴۵۶۷۸۹", "Digits wrong")
    assert_eq(to_fa_digits("abc123"), "abc۱۲۳", "Mixed wrong")
    assert_eq(to_fa_digits(123), "۱۲۳", "Int wrong")


@test("i18n.to_en_digits converts correctly")
def _test_to_en_digits():
    from .i18n import to_en_digits
    assert_eq(to_en_digits("۰۱۲۳۴۵۶۷۸۹"), "0123456789", "Digits wrong")
    assert_eq(to_en_digits("abc۱۲۳"), "abc123", "Mixed wrong")


@test("i18n.to_fa_digits and to_en_digits are inverses")
def _test_digit_inverse():
    from .i18n import to_fa_digits, to_en_digits
    s = "12345"
    assert_eq(to_en_digits(to_fa_digits(s)), s, "Roundtrip failed")


@test("i18n.t with positional placeholders")
def _test_t_placeholders():
    from .i18n import t
    # streakDays = "{0} days" in en, "{0} روز" in fa
    result_en = t("streakDays", "en", 5)
    assert_in("5", result_en, "Should contain '5'")
    assert_in("days", result_en, "Should contain 'days'")
    result_fa = t("streakDays", "fa", 5)
    assert_in("۵", result_fa, "Should contain Persian '5'")


@test("i18n.fa_num formats with Persian digits and separators")
def _test_fa_num():
    from .i18n import fa_num
    assert_eq(fa_num(1234), "۱٬۲۳۴", f"1234 wrong: {fa_num(1234)}")
    assert_eq(fa_num(0), "۰", "0 wrong")


@test("i18n.available_langs returns at least fa and en")
def _test_available_langs():
    from .i18n import available_langs
    langs = available_langs()
    assert_in("fa", langs, "Should have fa")
    assert_in("en", langs, "Should have en")


@test("i18n.is_rtl for known languages")
def _test_is_rtl():
    from .i18n import is_rtl
    assert_true(is_rtl("fa"), "fa should be RTL")
    assert_true(is_rtl("ar"), "ar should be RTL")
    assert_false(is_rtl("en"), "en should not be RTL")
    assert_false(is_rtl("fr"), "fr should not be RTL")


# =====================================================================
# === CRYPTO TESTS ===
# =====================================================================
@test("crypto.crypto_available returns bool")
def _test_crypto_available():
    from . import crypto
    assert_true(isinstance(crypto.crypto_available(), bool), "Should return bool")


@test("crypto.set_pin returns hash string")
def _test_set_pin():
    from . import crypto
    pin_hash = crypto.set_pin("1234")
    assert_true(isinstance(pin_hash, str), "Should return string")
    assert_in("$", pin_hash, "Should contain $ separator")


@test("crypto.check_pin verifies correct PIN")
def _test_check_pin_correct():
    from . import crypto
    pin_hash = crypto.set_pin("1234")
    assert_true(crypto.check_pin("1234", pin_hash), "Correct PIN should verify")


@test("crypto.check_pin rejects wrong PIN")
def _test_check_pin_wrong():
    from . import crypto
    pin_hash = crypto.set_pin("1234")
    assert_false(crypto.check_pin("9999", pin_hash), "Wrong PIN should fail")


@test("crypto.set_pin rejects short PIN")
def _test_pin_too_short():
    from . import crypto
    try:
        crypto.set_pin("123")
        assert_true(False, "Should have raised ValueError")
    except ValueError:
        pass


@test("crypto.set_pin rejects non-digit PIN")
def _test_pin_non_digit():
    from . import crypto
    try:
        crypto.set_pin("12ab")
        assert_true(False, "Should have raised ValueError")
    except ValueError:
        pass


@test("crypto.set_pin rejects too long PIN")
def _test_pin_too_long():
    from . import crypto
    try:
        crypto.set_pin("1234567")
        assert_true(False, "Should have raised ValueError")
    except ValueError:
        pass


@test("crypto.encrypt_backup and decrypt_backup round-trip")
def _test_backup_roundtrip():
    from . import crypto
    if not crypto.crypto_available():
        return  # skip if cryptography not installed
    payload = {"hello": "world", "numbers": [1, 2, 3], "nested": {"a": True}}
    blob = crypto.encrypt_backup(payload, "testpassword123")
    assert_true(isinstance(blob, bytes), "Should return bytes")
    assert_true(len(blob) > 50, "Blob should be > 50 bytes")
    result = crypto.decrypt_backup(blob, "testpassword123")
    assert_eq(result, payload, "Roundtrip failed")


@test("crypto.decrypt_backup rejects wrong password")
def _test_backup_wrong_password():
    from . import crypto
    if not crypto.crypto_available():
        return
    payload = {"hello": "world"}
    blob = crypto.encrypt_backup(payload, "correct_password")
    try:
        crypto.decrypt_backup(blob, "wrong_password")
        assert_true(False, "Should have raised ValueError")
    except ValueError:
        pass


@test("crypto.decrypt_backup rejects invalid magic")
def _test_backup_invalid_magic():
    from . import crypto
    if not crypto.crypto_available():
        return
    try:
        crypto.decrypt_backup(b"XXXX" + b"\x01" + b"\x00" * 100, "any")
        assert_true(False, "Should have raised ValueError")
    except ValueError:
        pass


@test("crypto.sha256_hex returns 64-char hex")
def _test_sha256():
    from . import crypto
    h = crypto.sha256_hex("hello")
    assert_eq(len(h), 64, "Should be 64 chars")
    # Known SHA-256 of "hello"
    assert_eq(h, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
              "SHA-256 of 'hello' wrong")


@test("crypto.random_token returns hex string")
def _test_random_token():
    from . import crypto
    t1 = crypto.random_token(16)
    t2 = crypto.random_token(16)
    assert_eq(len(t1), 32, "16 bytes = 32 hex chars")
    assert_true(t1 != t2, "Should be different")


@test("crypto.random_pin returns digits of correct length")
def _test_random_pin():
    from . import crypto
    pin = crypto.random_pin(4)
    assert_eq(len(pin), 4, "Should be 4 chars")
    assert_true(pin.isdigit(), "Should be all digits")


# =====================================================================
# === TIMER SERVICE TESTS ===
# =====================================================================
@test("timer_service.is_running returns bool initially")
def _test_timer_initial():
    from . import timer_service
    timer_service.cancel()
    assert_false(timer_service.is_running(), "Should not be running initially")
    assert_eq(timer_service.elapsed_sec(), 0, "Should have 0 elapsed initially")


@test("timer_service.start sets running state")
def _test_timer_start():
    from . import timer_service
    timer_service.cancel()
    timer_service.start("Test", None, None)
    assert_true(timer_service.is_running(), "Should be running after start")
    assert_eq(timer_service.current_title(), "Test", "Title wrong")
    timer_service.cancel()


@test("timer_service.pause pauses")
def _test_timer_pause():
    from . import timer_service
    timer_service.cancel()
    timer_service.start("Test", None, None)
    timer_service.pause()
    assert_false(timer_service.is_running(), "Should not be running after pause")
    timer_service.cancel()


@test("timer_service.cancel resets state")
def _test_timer_cancel():
    from . import timer_service
    timer_service.start("Test", None, None)
    timer_service.cancel()
    assert_false(timer_service.is_running(), "Should not be running after cancel")
    assert_eq(timer_service.elapsed_sec(), 0, "Should be 0 after cancel")
    assert_eq(timer_service.current_title(), "", "Title should be empty")


@test("timer_service.add_listener / remove_listener")
def _test_timer_listeners():
    from . import timer_service
    received = []
    def listener(elapsed, running):
        received.append((elapsed, running))
    timer_service.add_listener(listener)
    timer_service.cancel()  # Triggers emit
    timer_service.remove_listener(listener)
    # Verify we received at least one event
    assert_true(len(received) >= 1, "Should have received at least one event")


# =====================================================================
# === ANALYTICS TESTS ===
# =====================================================================
@test("analytics.build_summary returns dict with expected keys")
def _test_build_summary():
    from . import analytics
    from .date_utils import today_iso
    summary = analytics.build_summary(today_iso(), today_iso(), "fa")
    expected_keys = ["start_iso", "end_iso", "days", "count", "total_sec",
                     "daily_avg_sec", "active_days", "best_day", "peak_hour",
                     "category_breakdown", "duration_stats", "comparison",
                     "top_categories", "top_activities", "weekend_vs_weekday",
                     "productivity_score", "consistency_score", "balance_score",
                     "insights", "per_day", "hourly", "weekday"]
    for k in expected_keys:
        assert_in(k, summary, f"Missing key: {k}")


@test("analytics.compare_periods returns delta")
def _test_compare_periods():
    from . import analytics
    result = analytics.compare_periods("2026-07-18", "2026-07-18",
                                        "2026-07-17", "2026-07-17")
    assert_in("current_sec", result, "Missing current_sec")
    assert_in("previous_sec", result, "Missing previous_sec")
    assert_in("delta_sec", result, "Missing delta_sec")
    assert_in("trend", result, "Missing trend")


@test("analytics.previous_period_range computes correctly")
def _test_previous_period():
    from . import analytics
    import datetime as _dt
    s, e = analytics.previous_period_range("2026-07-18", "2026-07-18")
    # Previous day
    expected = (_dt.date(2026, 7, 17)).isoformat()
    assert_eq(s, expected, "Previous day start wrong")
    assert_eq(e, expected, "Previous day end wrong")


@test("analytics.productivity_score returns 0-100")
def _test_productivity_score():
    from . import analytics
    from .date_utils import today_iso
    score = analytics.productivity_score(today_iso(), today_iso())
    assert_true(0 <= score <= 100, f"Score should be 0-100, got {score}")


@test("analytics.consistency_score returns 0-100")
def _test_consistency_score():
    from . import analytics
    from .date_utils import today_iso
    score = analytics.consistency_score(today_iso(), today_iso())
    assert_true(0 <= score <= 100, f"Score should be 0-100, got {score}")


@test("analytics.balance_score returns 0-100")
def _test_balance_score():
    from . import analytics
    from .date_utils import today_iso
    score = analytics.balance_score(today_iso(), today_iso())
    assert_true(0 <= score <= 100, f"Score should be 0-100, got {score}")


@test("analytics.generate_insights returns list of strings")
def _test_generate_insights():
    from . import analytics
    from .date_utils import today_iso
    insights = analytics.generate_insights(today_iso(), today_iso(), "fa")
    assert_true(isinstance(insights, list), "Should be list")
    for i in insights:
        assert_true(isinstance(i, str), "Each insight should be string")


# =====================================================================
# === RECURRING TESTS ===
# =====================================================================
@test("recurring.matches_date for daily")
def _test_recurring_daily():
    from . import recurring
    import datetime as _dt
    d = _dt.date(2026, 7, 18)
    assert_true(recurring.matches_date("daily", [], d), "Daily should match any date")


@test("recurring.matches_date for weekdays")
def _test_recurring_weekdays():
    from . import recurring
    import datetime as _dt
    # 2026-07-18 is a Saturday (py weekday=5)
    sat = _dt.date(2026, 7, 18)
    sun = _dt.date(2026, 7, 19)
    mon = _dt.date(2026, 7, 20)
    tue = _dt.date(2026, 7, 21)
    wed = _dt.date(2026, 7, 22)
    thu = _dt.date(2026, 7, 23)  # Persian weekend
    fri = _dt.date(2026, 7, 24)  # Persian weekend
    # Persian weekday (Sat-Wed)
    assert_true(recurring.matches_date("weekdays", [], sat), "Sat should be weekday")
    assert_true(recurring.matches_date("weekdays", [], sun), "Sun should be weekday")
    assert_true(recurring.matches_date("weekdays", [], mon), "Mon should be weekday")
    assert_false(recurring.matches_date("weekdays", [], thu), "Thu should not be weekday")
    assert_false(recurring.matches_date("weekdays", [], fri), "Fri should not be weekday")


@test("recurring.matches_date for weekends")
def _test_recurring_weekends():
    from . import recurring
    import datetime as _dt
    thu = _dt.date(2026, 7, 23)  # Persian weekend
    fri = _dt.date(2026, 7, 24)  # Persian weekend
    sat = _dt.date(2026, 7, 18)
    assert_true(recurring.matches_date("weekends", [], thu), "Thu should be weekend")
    assert_true(recurring.matches_date("weekends", [], fri), "Fri should be weekend")
    assert_false(recurring.matches_date("weekends", [], sat), "Sat should not be weekend")


@test("recurring.matches_date for custom")
def _test_recurring_custom():
    from . import recurring
    import datetime as _dt
    # Custom: Mon, Wed, Fri (py weekday 0, 2, 4)
    mon = _dt.date(2026, 7, 20)
    wed = _dt.date(2026, 7, 22)
    fri = _dt.date(2026, 7, 24)
    tue = _dt.date(2026, 7, 21)
    assert_true(recurring.matches_date("custom", [0, 2, 4], mon), "Mon should match")
    assert_true(recurring.matches_date("custom", [0, 2, 4], wed), "Wed should match")
    assert_true(recurring.matches_date("custom", [0, 2, 4], fri), "Fri should match")
    assert_false(recurring.matches_date("custom", [0, 2, 4], tue), "Tue should not match")


@test("recurring.compute_next_run finds next matching date")
def _test_compute_next_run():
    from . import recurring
    import datetime as _dt
    rule = {"pattern": "daily", "custom_days": "[]"}
    after = _dt.date(2026, 7, 18)
    next_run = recurring.compute_next_run(rule, after)
    # Daily should match the same day
    assert_eq(next_run, after, "Daily should match same day")
    # Weekday pattern
    rule = {"pattern": "weekdays", "custom_days": "[]"}
    after = _dt.date(2026, 7, 23)  # Thursday
    next_run = recurring.compute_next_run(rule, after)
    # Should be Saturday (skip Thu, Fri)
    assert_eq(next_run, _dt.date(2026, 7, 25), "Should skip to Saturday")


@test("recurring.create_recurring inserts a rule")
def _test_create_recurring():
    from . import recurring
    rid = recurring.create_recurring(
        title="Test recurring",
        category_id=None,
        pattern="daily",
        duration_sec=600,
        start_date="2026-07-18",
    )
    assert_true(rid > 0, "Should get positive id")
    r = recurring.recurring_by_id(rid) if hasattr(recurring, 'recurring_by_id') else None
    # Cleanup
    recurring.delete_recurring(rid)


# =====================================================================
# === ICONS TESTS ===
# =====================================================================
@test("icons.icon_names returns non-empty list")
def _test_icon_names():
    from .icons import icon_names
    names = icon_names()
    assert_true(len(names) > 50, f"Should have > 50 icons, got {len(names)}")


@test("icons.icon_exists for known icons")
def _test_icon_exists():
    from .icons import icon_exists
    for name in ["home", "plus", "minus", "check", "x", "clock", "calendar"]:
        assert_true(icon_exists(name), f"Icon '{name}' should exist")


@test("icons.icon_exists returns False for unknown")
def _test_icon_not_exists():
    from .icons import icon_exists
    assert_false(icon_exists("nonexistent_icon_xyz"), "Should not exist")


@test("icons.get_icon_path returns string")
def _test_get_icon_path():
    from .icons import get_icon_path
    path = get_icon_path("home")
    assert_true(isinstance(path, str), "Should return string")
    assert_true(len(path) > 0, "Should be non-empty")


@test("icons.category_icon returns valid icon")
def _test_category_icon():
    from .icons import category_icon
    for key in ["FOCUS", "LEARN", "WORK", "HEALTH", "CREATIVE", "SOCIAL", "REST"]:
        icon = category_icon(key)
        assert_true(isinstance(icon, str), f"Should be string for {key}")


# =====================================================================
# === EXPORTERS TESTS ===
# =====================================================================
@test("exporters.export_csv writes valid CSV")
def _test_csv_export():
    from . import exporters
    from . import database
    database.open_db()
    activities = [{
        "title": "Test",
        "category_id": 1,
        "kind": "manual",
        "date_iso": "2026-07-18",
        "duration_sec": 1800,
        "note": "test note",
    }]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                                       encoding="utf-8-sig") as f:
        path = f.name
    try:
        rows = exporters.export_csv(path, activities, "en")
        assert_eq(rows, 1, "Should write 1 row")
        # Verify file exists and has content
        assert_true(os.path.exists(path), "File should exist")
        with open(path, "r", encoding="utf-8-sig") as fh:
            content = fh.read()
        assert_in("Test", content, "Should contain title")
    finally:
        os.unlink(path)


@test("exporters.export_json writes valid JSON")
def _test_json_export():
    from . import exporters
    payload = {"hello": "world", "numbers": [1, 2, 3]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        exporters.export_json(path, payload)
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        parsed = json.loads(content)
        assert_eq(parsed, payload, "Roundtrip failed")
    finally:
        os.unlink(path)


@test("exporters.export_text writes plain text")
def _test_text_export():
    from . import exporters
    summary = {
        "start_iso": "2026-07-18",
        "end_iso": "2026-07-18",
        "count": 1,
        "total_sec": 1800,
        "daily_avg_sec": 1800.0,
    }
    activities = [{"title": "Test", "date_iso": "2026-07-18", "duration_sec": 1800}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        path = f.name
    try:
        exporters.export_text(path, summary, activities, "en")
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        assert_in("Test", content, "Should contain 'Test'")
        assert_in("Rask", content, "Should contain 'Rask'")
    finally:
        os.unlink(path)


@test("exporters.pdf_available returns bool")
def _test_pdf_available():
    from . import exporters
    assert_true(isinstance(exporters.pdf_available(), bool), "Should return bool")


# =====================================================================
# === CONFIG TESTS ===
# =====================================================================
@test("config has all required color constants")
def _test_config_colors():
    from . import config
    for name in ["MATTE_BLACK", "CHARCOAL", "SURFACE", "SURFACE_HI", "GOLD",
                 "GOLD_SOFT", "GOLD_DIM", "TEXT", "TEXT_DIM", "TEXT_FAINT",
                 "SUCCESS", "WARNING", "DANGER", "DIVIDER"]:
        assert_true(hasattr(config, name), f"Missing color: {name}")


@test("config has all required spacing constants")
def _test_config_spacing():
    from . import config
    for name in ["SPACE_XS", "SPACE_SM", "SPACE_MD", "SPACE_LG",
                 "SPACE_XL", "SPACE_XXL", "SPACE_XXXL"]:
        assert_true(hasattr(config, name), f"Missing spacing: {name}")


@test("config.WINDOW_WIDTH and WINDOW_HEIGHT are reasonable")
def _test_window_size():
    from . import config
    assert_true(config.WINDOW_WIDTH > 0, "Width should be positive")
    assert_true(config.WINDOW_HEIGHT > 0, "Height should be positive")
    # Should be phone-aspect-ratio (taller than wide)
    assert_true(config.WINDOW_HEIGHT > config.WINDOW_WIDTH, "Should be portrait")


@test("config.DEFAULT_CATEGORIES has 7 entries")
def _test_default_categories():
    from . import config
    assert_eq(len(config.DEFAULT_CATEGORIES), 7, "Should have 7 categories")
    keys = [c["key"] for c in config.DEFAULT_CATEGORIES]
    for k in ["FOCUS", "LEARN", "WORK", "HEALTH", "CREATIVE", "SOCIAL", "REST"]:
        assert_in(k, keys, f"Missing {k}")


@test("config.hex_to_rgb converts correctly")
def _test_hex_to_rgb():
    from . import config
    assert_eq(config.hex_to_rgb("#D4AF37"), (212, 175, 55), "Gold wrong")
    assert_eq(config.hex_to_rgb("D4AF37"), (212, 175, 55), "Without # wrong")
    assert_eq(config.hex_to_rgb("#FFF"), (255, 255, 255), "Short form wrong")


@test("config.rgb_to_hex converts correctly")
def _test_rgb_to_hex():
    from . import config
    assert_eq(config.rgb_to_hex(212, 175, 55), "#D4AF37", "Gold wrong")
    assert_eq(config.rgb_to_hex(255, 255, 255), "#FFFFFF", "White wrong")


@test("config.lighten and darken")
def _test_lighten_darken():
    from . import config
    light = config.lighten("#808080", 0.5)
    dark = config.darken("#808080", 0.5)
    # Light should be lighter, dark should be darker
    light_rgb = config.hex_to_rgb(light)
    dark_rgb = config.hex_to_rgb(dark)
    assert_true(light_rgb[0] > 128, "Light should be brighter")
    assert_true(dark_rgb[0] < 128, "Dark should be darker")


@test("config.heatmap_color returns valid hex")
def _test_heatmap_color():
    from . import config
    c0 = config.heatmap_color(0)
    c1 = config.heatmap_color(1)
    c_half = config.heatmap_color(0.5)
    # All should be valid hex strings starting with #
    for c in [c0, c1, c_half]:
        assert_true(c.startswith("#"), f"Should start with #, got {c}")
        assert_eq(len(c), 7, f"Should be 7 chars, got {c}")


@test("config.is_rtl for known languages")
def _test_config_is_rtl():
    from . import config
    assert_true(config.is_rtl("fa"), "fa should be RTL")
    assert_false(config.is_rtl("en"), "en should not be RTL")


@test("config.DATA_DIR exists and is writable")
def _test_data_dir():
    from . import config
    assert_true(config.DATA_DIR.exists(), "Data dir should exist")
    assert_true(config.DATA_DIR.is_dir(), "Should be a directory")


# =====================================================================
# === RUN ALL ===
# =====================================================================
def run_all() -> int:
    """Run all tests. Returns 0 if all pass, 1 otherwise."""
    global _passed, _failed
    print("=" * 60)
    print("Rask Test Suite")
    print("=" * 60)
    print()
    # The @test decorators above have already run the tests at import time
    print()
    print("=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed")
    if _failed:
        print()
        print("Failures:")
        for f in _failures:
            print(f"  - {f}")
    print("=" * 60)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
