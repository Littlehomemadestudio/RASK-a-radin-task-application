"""
rask.features.mood_tracker
==========================

Standalone mood & energy tracker.

Distinct from :mod:`rask.features.journal` (which is a richer daily
diary), the mood tracker is a quick single-tap mood log designed for
multiple entries per day.  Use cases:

  • "How am I feeling right now?" prompts throughout the day
  • Correlating mood with activity categories (e.g. "after Reading
    mood is +0.4 on average")
  • Building a mood-distribution chart for the Insights screen

Schema
------

::

    CREATE TABLE mood_entries (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        date_iso        TEXT NOT NULL,
        time_hhmm       TEXT NOT NULL,        -- "HH:MM"
        mood            INTEGER NOT NULL,     -- 1..5
        energy          INTEGER,
        notes           TEXT,
        triggers_json   TEXT,
        created_at      TEXT NOT NULL
    );

Events
------

  ``mood.added``       — {entry: dict}
  ``mood.updated``     — {id, fields: dict, entry: dict}
  ``mood.deleted``     — {id}
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import add_days, today_iso

__all__ = [
    "MoodEntry",
    "MoodService",
    "mood_service",
    "MOOD_EMOJIS",
    "MOOD_LABELS_FA",
    "MOOD_LABELS_EN",
]

_log = get_logger("features.mood")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

#: Emoji shown for each mood level (1..5).
MOOD_EMOJIS: Dict[int, str] = {
    1: "😞",
    2: "😕",
    3: "😐",
    4: "🙂",
    5: "😄",
}

#: Persian labels for each mood level.
MOOD_LABELS_FA: Dict[int, str] = {
    1: "خیلی بد",
    2: "بد",
    3: "معمولی",
    4: "خوب",
    5: "عالی",
}

#: English labels for each mood level.
MOOD_LABELS_EN: Dict[int, str] = {
    1: "Very Bad",
    2: "Bad",
    3: "Neutral",
    4: "Good",
    5: "Great",
}


SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS mood_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date_iso        TEXT NOT NULL,
    time_hhmm       TEXT NOT NULL,
    mood            INTEGER NOT NULL,
    energy          INTEGER,
    notes           TEXT,
    triggers_json   TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mood_date ON mood_entries(date_iso);
CREATE INDEX IF NOT EXISTS idx_mood_mood ON mood_entries(mood);
"""


# =============================================================================
# === Data class                                                             ===
# =============================================================================

@dataclass
class MoodEntry:
    """A single mood reading."""

    date_iso: str
    time_hhmm: str
    mood: int
    energy: Optional[int] = None
    notes: Optional[str] = None
    triggers: List[str] = field(default_factory=list)
    id: Optional[int] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "MoodEntry":
        def _loads(s: Any) -> List[str]:
            if not s:
                return []
            if isinstance(s, list):
                return list(s)
            try:
                v = json.loads(s)
                return list(v) if isinstance(v, list) else []
            except Exception:  # noqa: BLE001
                return []
        return cls(
            id=int(row["id"]) if row.get("id") is not None else None,
            date_iso=row["date_iso"],
            time_hhmm=row["time_hhmm"],
            mood=int(row["mood"]),
            energy=int(row["energy"]) if row.get("energy") is not None else None,
            notes=row.get("notes"),
            triggers=_loads(row.get("triggers_json")),
            created_at=row.get("created_at"),
        )


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _validate_mood(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"mood must be an int 1..5, got {v!r}")
    if n < 1 or n > 5:
        raise ValueError(f"mood must be 1..5, got {n}")
    return n


def _validate_energy(v: Optional[int]) -> Optional[int]:
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if n < 1 or n > 5:
        return None
    return n


def _json_dumps(v: Any) -> str:
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return "[]"


def _now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


# =============================================================================
# === Schema bootstrap                                                       ===
# =============================================================================

_schema_initialized: bool = False
_schema_lock = threading.Lock()


def _ensure_schema() -> None:
    global _schema_initialized
    if _schema_initialized:
        return
    with _schema_lock:
        if _schema_initialized:
            return
        try:
            conn = db.get_conn()
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            _schema_initialized = True
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})


# =============================================================================
# === MoodService                                                            ===
# =============================================================================

class MoodService:
    """Mood & energy tracker."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        _ensure_schema()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, date_iso: Optional[str] = None, mood: int = 3,
            energy: Optional[int] = None, notes: Optional[str] = None,
            triggers: Optional[List[str]] = None,
            time_hhmm: Optional[str] = None) -> int:
        """Add a mood entry.  Returns the new id (0 on failure)."""
        date_iso = (date_iso or today_iso())[:10]
        mood = _validate_mood(mood)
        energy = _validate_energy(energy)
        time_hhmm = time_hhmm or _now_hhmm()
        if not (isinstance(time_hhmm, str) and ":" in time_hhmm):
            time_hhmm = _now_hhmm()
        triggers = triggers or []
        triggers = [str(t).strip()[:40] for t in triggers if str(t).strip()][:20]
        now = _now_iso()
        try:
            conn = db.get_conn()
            cur = conn.execute(
                "INSERT INTO mood_entries(date_iso, time_hhmm, mood, energy, "
                "notes, triggers_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (date_iso, time_hhmm, mood, energy, notes,
                 _json_dumps(triggers), now),
            )
            conn.commit()
            new_id = int(cur.lastrowid or 0)
            entry = self.get(new_id)
            bus.publish("mood.added", {"entry": entry.to_dict() if entry else {}})
            _log.info("Mood entry added: id=%d mood=%d date=%s",
                      new_id, mood, date_iso)
            return new_id
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"date_iso": date_iso, "mood": mood})
            return 0

    def update(self, id: int, **fields: Any) -> Optional[MoodEntry]:
        if not isinstance(id, int) or id <= 0:
            return None
        existing = self.get(id)
        if existing is None:
            return None
        allowed = {"date_iso", "time_hhmm", "mood", "energy", "notes", "triggers"}
        updates: List[str] = []
        values: List[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "mood":
                v = _validate_mood(v)
            if k == "energy":
                v = _validate_energy(v)
            if k == "triggers":
                v = [str(t).strip()[:40] for t in (v or []) if str(t).strip()][:20]
                updates.append("triggers_json = ?")
                values.append(_json_dumps(v))
                continue
            updates.append(f"{k} = ?")
            values.append(v)
        if not updates:
            return existing
        try:
            conn = db.get_conn()
            conn.execute(
                f"UPDATE mood_entries SET {', '.join(updates)} WHERE id = ?",
                values + [id])
            conn.commit()
            updated = self.get(id)
            bus.publish("mood.updated",
                        {"id": id, "fields": fields,
                         "entry": updated.to_dict() if updated else None})
            return updated
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return existing

    def delete(self, id: int) -> bool:
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            conn = db.get_conn()
            cur = conn.execute("DELETE FROM mood_entries WHERE id = ?", (id,))
            conn.commit()
            ok = (cur.rowcount or 0) > 0
            if ok:
                bus.publish("mood.deleted", {"id": id})
            return ok
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False

    def get(self, id: int) -> Optional[MoodEntry]:
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            cur = db.get_conn().execute(
                "SELECT * FROM mood_entries WHERE id = ?", (id,))
            row = cur.fetchone()
            if not row:
                return None
            return MoodEntry.from_row({k: row[k] for k in row.keys()})
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None

    def get_by_date(self, date_iso: str) -> List[MoodEntry]:
        """Return all mood entries for the given date, oldest first."""
        try:
            cur = db.get_conn().execute(
                "SELECT * FROM mood_entries WHERE date_iso = ? "
                "ORDER BY time_hhmm ASC",
                (date_iso[:10],))
            return [MoodEntry.from_row({k: r[k] for k in r.keys()})
                    for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"date_iso": date_iso})
            return []

    def list(self, date_from: Optional[str] = None,
             date_to: Optional[str] = None,
             limit: int = 1000) -> List[MoodEntry]:
        try:
            where = []
            args: List[Any] = []
            if date_from:
                where.append("date_iso >= ?")
                args.append(date_from[:10])
            if date_to:
                where.append("date_iso <= ?")
                args.append(date_to[:10])
            sql = "SELECT * FROM mood_entries"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY date_iso DESC, time_hhmm DESC LIMIT ?"
            args.append(int(limit))
            cur = db.get_conn().execute(sql, args)
            return [MoodEntry.from_row({k: r[k] for k in r.keys()})
                    for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"date_from": date_from, "date_to": date_to})
            return []

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    def average_mood(self, days: int = 30) -> float:
        if days <= 0:
            days = 30
        date_from = add_days(today_iso(), -(days - 1))
        try:
            cur = db.get_conn().execute(
                "SELECT AVG(mood) AS avg FROM mood_entries WHERE date_iso >= ?",
                (date_from,))
            row = cur.fetchone()
            if not row or row["avg"] is None:
                return 0.0
            return round(float(row["avg"]), 2)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"days": days})
            return 0.0

    def average_energy(self, days: int = 30) -> float:
        if days <= 0:
            days = 30
        date_from = add_days(today_iso(), -(days - 1))
        try:
            cur = db.get_conn().execute(
                "SELECT AVG(energy) AS avg FROM mood_entries "
                "WHERE energy IS NOT NULL AND date_iso >= ?",
                (date_from,))
            row = cur.fetchone()
            if not row or row["avg"] is None:
                return 0.0
            return round(float(row["avg"]), 2)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"days": days})
            return 0.0

    def mood_distribution(self, days: int = 30) -> Dict[int, int]:
        """Return ``{1: N, 2: N, 3: N, 4: N, 5: N}`` for the last `days` days."""
        if days <= 0:
            days = 30
        date_from = add_days(today_iso(), -(days - 1))
        try:
            cur = db.get_conn().execute(
                "SELECT mood, COUNT(*) AS c FROM mood_entries "
                "WHERE date_iso >= ? GROUP BY mood",
                (date_from,))
            out = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for r in cur.fetchall():
                out[int(r["mood"])] = int(r["c"])
            return out
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"days": days})
            return {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    def trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return ``[{date_iso, mood_avg, energy_avg, count}]`` per day."""
        if days <= 0:
            days = 30
        date_from = add_days(today_iso(), -(days - 1))
        try:
            cur = db.get_conn().execute(
                "SELECT date_iso, AVG(mood) AS mood_avg, "
                "AVG(energy) AS energy_avg, COUNT(*) AS count "
                "FROM mood_entries WHERE date_iso >= ? "
                "GROUP BY date_iso ORDER BY date_iso ASC",
                (date_from,))
            return [
                {
                    "date_iso": r["date_iso"],
                    "mood_avg": round(float(r["mood_avg"]), 2)
                                if r["mood_avg"] is not None else None,
                    "energy_avg": round(float(r["energy_avg"]), 2)
                                   if r["energy_avg"] is not None else None,
                    "count": int(r["count"]),
                }
                for r in cur.fetchall()
            ]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"days": days})
            return []

    # ------------------------------------------------------------------
    # Correlation with activities
    # ------------------------------------------------------------------

    def correlation_with_activities(self) -> Dict[str, Any]:
        """Correlate mood with activity categories.

        For each category, find mood entries logged on the same day as
        an activity in that category, and compute the average mood on
        those days vs. the overall average mood.  Returns a dict::

            {
                "overall_avg": float,
                "by_category": [
                    {
                        "category_id": int,
                        "category_name": str,
                        "category_color": str,
                        "avg_mood": float,
                        "delta": float,        # avg_mood - overall_avg
                        "sample_size": int,
                    }, ...
                ]
            }
        """
        overall = self.average_mood(30)
        try:
            # Build a map of date -> set of category_ids with activity that day.
            from ..database import activity_list
            date_from = add_days(today_iso(), -29)
            acts = activity_list(date_from=date_from, limit=10000)
            date_to_cats: Dict[str, set] = {}
            for a in acts:
                d = a.get("date_iso")
                cid = a.get("category_id")
                if d and cid:
                    date_to_cats.setdefault(d, set()).add(int(cid))

            # Build a map of date -> list of mood readings.
            date_to_moods: Dict[str, List[int]] = {}
            for entry in self.list(date_from=date_from, limit=10000):
                date_to_moods.setdefault(entry.date_iso, []).append(entry.mood)

            # Now aggregate per category.
            cat_to_moods: Dict[int, List[int]] = {}
            from ..database import category_list
            cat_map = {int(c["id"]): c for c in category_list()}
            for d, cats in date_to_cats.items():
                moods = date_to_moods.get(d)
                if not moods:
                    continue
                for cid in cats:
                    cat_to_moods.setdefault(cid, []).extend(moods)

            out: List[Dict[str, Any]] = []
            for cid, moods in cat_to_moods.items():
                if not moods:
                    continue
                avg = round(sum(moods) / len(moods), 2)
                cat = cat_map.get(cid, {})
                out.append({
                    "category_id": cid,
                    "category_name": cat.get("name_fa") or cat.get("name_en") or f"#{cid}",
                    "category_color": cat.get("color") or "#9A9A9F",
                    "avg_mood": avg,
                    "delta": round(avg - overall, 2),
                    "sample_size": len(moods),
                })
            out.sort(key=lambda x: x["delta"], reverse=True)
            return {"overall_avg": overall, "by_category": out}
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return {"overall_avg": overall, "by_category": []}

    def count(self) -> int:
        try:
            cur = db.get_conn().execute("SELECT COUNT(*) AS c FROM mood_entries")
            row = cur.fetchone()
            return int(row["c"]) if row else 0
        except Exception:  # noqa: BLE001
            return 0

    def count_today(self) -> int:
        try:
            cur = db.get_conn().execute(
                "SELECT COUNT(*) AS c FROM mood_entries WHERE date_iso = ?",
                (today_iso(),))
            row = cur.fetchone()
            return int(row["c"]) if row else 0
        except Exception:  # noqa: BLE001
            return 0

    def label_for(self, mood: int, lang: str = "fa") -> str:
        """Return a localized label for a mood value (1..5)."""
        if lang == "fa":
            return MOOD_LABELS_FA.get(mood, str(mood))
        return MOOD_LABELS_EN.get(mood, str(mood))

    def emoji_for(self, mood: int) -> str:
        return MOOD_EMOJIS.get(mood, "❓")


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

mood_service: MoodService = MoodService()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== mood_tracker self-tests ===")
    try:
        eid = mood_service.add(mood=4, energy=3, notes="test")
        assert eid > 0
        got = mood_service.get(eid)
        assert got is not None and got.mood == 4
        mood_service.delete(eid)
        print("  OK   basic CRUD")
    except AssertionError as e:
        print(f"  FAIL: {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL (exception): {e}")
        failed += 1
    print(f"\n{1 if failed else 0} failed.")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
