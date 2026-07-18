"""
rask.features.journal
=====================

Daily journal entries with mood, energy, gratitudes, and improvements.

Each journal entry is tied to a single calendar date (one entry per
day, optionally).  The entry captures:

  • ``mood`` — 1..5 (1=terrible, 5=great)
  • ``energy`` — 1..5 (1=exhausted, 5=energized)
  • ``title`` — short headline for the day
  • ``body`` — free-form long-form text
  • ``tags`` — list of strings (for search/filter)
  • ``gratitudes`` — list of strings (3-item gratitude practice)
  • ``improvements`` — list of strings (what to do better tomorrow)

The service exposes CRUD + range queries + search + trend analytics
(mood/energy over time) + streak counting.

Schema
------

::

    CREATE TABLE journal_entries (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        date_iso        TEXT NOT NULL UNIQUE,
        mood            INTEGER,
        energy          INTEGER,
        title           TEXT,
        body            TEXT,
        tags_json       TEXT,
        gratitudes_json TEXT,
        improvements_json TEXT,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    );

Events
------

  ``journal.added``       — {entry: dict}
  ``journal.updated``     — {id, fields: dict, entry: dict}
  ``journal.deleted``     — {id, date_iso}
  ``journal.streak_changed`` — {streak: int, best: int}
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import add_days, days_between, today_iso

__all__ = [
    "JournalEntry",
    "JournalService",
    "journal_service",
]

_log = get_logger("features.journal")


SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS journal_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date_iso        TEXT NOT NULL UNIQUE,
    mood            INTEGER,
    energy          INTEGER,
    title           TEXT,
    body            TEXT,
    tags_json       TEXT,
    gratitudes_json TEXT,
    improvements_json TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journal_date ON journal_entries(date_iso);
CREATE INDEX IF NOT EXISTS idx_journal_mood ON journal_entries(mood);
CREATE INDEX IF NOT EXISTS idx_journal_energy ON journal_entries(energy);
"""


# =============================================================================
# === Data class                                                             ===
# =============================================================================

@dataclass
class JournalEntry:
    """A single journal entry for a single date."""

    date_iso: str
    mood: Optional[int] = None
    energy: Optional[int] = None
    title: Optional[str] = None
    body: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    gratitudes: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "JournalEntry":
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
            mood=int(row["mood"]) if row.get("mood") is not None else None,
            energy=int(row["energy"]) if row.get("energy") is not None else None,
            title=row.get("title"),
            body=row.get("body"),
            tags=_loads(row.get("tags_json")),
            gratitudes=_loads(row.get("gratitudes_json")),
            improvements=_loads(row.get("improvements_json")),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _validate_mood_energy(v: Optional[int]) -> Optional[int]:
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
            _log.debug("journal_entries schema initialized")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})


# =============================================================================
# === JournalService                                                         ===
# =============================================================================

class JournalService:
    """CRUD + analytics for daily journal entries."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        _ensure_schema()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, entry: JournalEntry) -> int:
        """Add a journal entry.  Returns the new row id (0 on failure).

        If an entry for the same date already exists, raises
        ``ValueError``.  Use :meth:`update` instead.
        """
        if not entry.date_iso or len(entry.date_iso) < 10:
            raise ValueError("JournalEntry.date_iso must be a valid YYYY-MM-DD")
        # Validate mood/energy.
        entry.mood = _validate_mood_energy(entry.mood)
        entry.energy = _validate_mood_energy(entry.energy)
        # Sanitize tags.
        if entry.tags:
            entry.tags = [str(t).strip()[:40] for t in entry.tags if str(t).strip()][:20]
        else:
            entry.tags = []
        if not entry.gratitudes:
            entry.gratitudes = []
        if not entry.improvements:
            entry.improvements = []

        now = _now_iso()
        try:
            conn = db.get_conn()
            cur = conn.execute(
                "INSERT INTO journal_entries(date_iso, mood, energy, title, "
                "body, tags_json, gratitudes_json, improvements_json, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entry.date_iso, entry.mood, entry.energy, entry.title,
                 entry.body, _json_dumps(entry.tags),
                 _json_dumps(entry.gratitudes),
                 _json_dumps(entry.improvements), now, now),
            )
            conn.commit()
            new_id = int(cur.lastrowid or 0)
            entry.id = new_id
            entry.created_at = now
            entry.updated_at = now
            bus.publish("journal.added", {"entry": entry.to_dict()})
            _log.info("Journal entry added: id=%d date=%s", new_id, entry.date_iso)
            self._maybe_publish_streak()
            return new_id
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"date_iso": entry.date_iso})
            return 0

    def update(self, id: int, **fields: Any) -> Optional[JournalEntry]:
        if not isinstance(id, int) or id <= 0:
            return None
        existing = self.get(id)
        if existing is None:
            return None

        allowed = {
            "date_iso", "mood", "energy", "title", "body",
            "tags", "gratitudes", "improvements",
        }
        updates: List[str] = []
        values: List[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "mood" or k == "energy":
                v = _validate_mood_energy(v)
            if k in ("tags", "gratitudes", "improvements"):
                if v is None:
                    v = []
                if not isinstance(v, list):
                    v = list(v) if v else []
                if k == "tags":
                    v = [str(t).strip()[:40] for t in v if str(t).strip()][:20]
                updates.append(f"{k}_json = ?")
                values.append(_json_dumps(v))
            else:
                updates.append(f"{k} = ?")
                values.append(v)

        if not updates:
            return existing

        updates.append("updated_at = ?")
        values.append(_now_iso())
        values.append(id)

        try:
            conn = db.get_conn()
            conn.execute(
                f"UPDATE journal_entries SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            conn.commit()
            updated = self.get(id)
            bus.publish("journal.updated",
                        {"id": id, "fields": fields,
                         "entry": updated.to_dict() if updated else None})
            return updated
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return existing

    def delete(self, id: int) -> bool:
        if not isinstance(id, int) or id <= 0:
            return False
        existing = self.get(id)
        if existing is None:
            return False
        try:
            conn = db.get_conn()
            cur = conn.execute("DELETE FROM journal_entries WHERE id = ?", (id,))
            conn.commit()
            ok = (cur.rowcount or 0) > 0
            if ok:
                bus.publish("journal.deleted",
                            {"id": id, "date_iso": existing.date_iso})
                self._maybe_publish_streak()
            return ok
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False

    def get(self, id: int) -> Optional[JournalEntry]:
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            cur = db.get_conn().execute(
                "SELECT * FROM journal_entries WHERE id = ?", (id,))
            row = cur.fetchone()
            if not row:
                return None
            return JournalEntry.from_row({k: row[k] for k in row.keys()})
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None

    def get_by_date(self, date_iso: str) -> Optional[JournalEntry]:
        """Return the entry for the given date, or ``None``."""
        try:
            cur = db.get_conn().execute(
                "SELECT * FROM journal_entries WHERE date_iso = ?",
                (date_iso[:10],))
            row = cur.fetchone()
            if not row:
                return None
            return JournalEntry.from_row({k: row[k] for k in row.keys()})
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"date_iso": date_iso})
            return None

    def list(self, date_from: Optional[str] = None,
             date_to: Optional[str] = None) -> List[JournalEntry]:
        """List entries in a date range (inclusive).  Sorted newest first."""
        try:
            where = []
            args: List[Any] = []
            if date_from:
                where.append("date_iso >= ?")
                args.append(date_from[:10])
            if date_to:
                where.append("date_iso <= ?")
                args.append(date_to[:10])
            sql = "SELECT * FROM journal_entries"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY date_iso DESC, id DESC"
            cur = db.get_conn().execute(sql, args)
            return [JournalEntry.from_row({k: r[k] for k in r.keys()})
                    for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"date_from": date_from, "date_to": date_to})
            return []

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 50) -> List[JournalEntry]:
        """Full-text search across title and body."""
        if not query or not query.strip():
            return []
        q = f"%{query.strip()}%"
        try:
            cur = db.get_conn().execute(
                "SELECT * FROM journal_entries "
                "WHERE title LIKE ? OR body LIKE ? "
                "ORDER BY date_iso DESC LIMIT ?",
                (q, q, int(limit)))
            return [JournalEntry.from_row({k: r[k] for k in r.keys()})
                    for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"query": query})
            return []

    # ------------------------------------------------------------------
    # Trend analytics
    # ------------------------------------------------------------------

    def mood_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return ``[{date_iso, mood}]`` for the last `days` days.

        Days with no entry are omitted (caller can fill gaps).
        """
        return self._trend("mood", days)

    def energy_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return ``[{date_iso, energy}]`` for the last `days` days."""
        return self._trend("energy", days)

    def _trend(self, field: str, days: int) -> List[Dict[str, Any]]:
        if days <= 0:
            days = 30
        date_from = add_days(today_iso(), -(days - 1))
        try:
            cur = db.get_conn().execute(
                f"SELECT date_iso, {field} FROM journal_entries "
                f"WHERE date_iso >= ? AND {field} IS NOT NULL "
                f"ORDER BY date_iso ASC",
                (date_from,))
            return [{"date_iso": r["date_iso"], field: int(r[field])}
                    for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"field": field, "days": days})
            return []

    # ------------------------------------------------------------------
    # Streak
    # ------------------------------------------------------------------

    def streak(self) -> int:
        """Return the current consecutive-day streak (today or yesterday back).

        If today has an entry, the streak counts today backward.  If
        today doesn't but yesterday does, the streak counts yesterday
        backward (so the streak isn't broken until a full day passes
        without an entry).
        """
        try:
            cur = db.get_conn().execute(
                "SELECT date_iso FROM journal_entries ORDER BY date_iso DESC")
            dates = [r["date_iso"] for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

        if not dates:
            return 0

        today = today_iso()
        yesterday = add_days(today, -1)

        # Determine starting point.
        if dates[0] == today:
            start = today
        elif dates[0] == yesterday:
            start = yesterday
        else:
            # Most recent entry is older than yesterday — streak broken.
            return 0

        date_set = set(dates)
        streak = 0
        cur_date = start
        while cur_date in date_set:
            streak += 1
            cur_date = add_days(cur_date, -1)
        return streak

    def best_streak(self) -> int:
        """Return the longest historical streak (in days)."""
        try:
            cur = db.get_conn().execute(
                "SELECT date_iso FROM journal_entries ORDER BY date_iso ASC")
            dates = [r["date_iso"] for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0
        if not dates:
            return 0
        best = 1
        current = 1
        for i in range(1, len(dates)):
            try:
                d1 = date.fromisoformat(dates[i - 1])
                d2 = date.fromisoformat(dates[i])
                if (d2 - d1).days == 1:
                    current += 1
                    if current > best:
                        best = current
                else:
                    current = 1
            except Exception:  # noqa: BLE001
                current = 1
        return best

    def _maybe_publish_streak(self) -> None:
        try:
            current = self.streak()
            best = self.best_streak()
            bus.publish("journal.streak_changed",
                        {"streak": current, "best": best})
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    def average_mood(self, days: int = 30) -> float:
        """Average mood over the last `days` days (0.0 if no entries)."""
        try:
            date_from = add_days(today_iso(), -(days - 1))
            cur = db.get_conn().execute(
                "SELECT AVG(mood) AS avg FROM journal_entries "
                "WHERE mood IS NOT NULL AND date_iso >= ?",
                (date_from,))
            row = cur.fetchone()
            if not row or row["avg"] is None:
                return 0.0
            return round(float(row["avg"]), 2)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"days": days})
            return 0.0

    def average_energy(self, days: int = 30) -> float:
        """Average energy over the last `days` days."""
        try:
            date_from = add_days(today_iso(), -(days - 1))
            cur = db.get_conn().execute(
                "SELECT AVG(energy) AS avg FROM journal_entries "
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
        try:
            date_from = add_days(today_iso(), -(days - 1))
            cur = db.get_conn().execute(
                "SELECT mood, COUNT(*) AS c FROM journal_entries "
                "WHERE mood IS NOT NULL AND date_iso >= ? "
                "GROUP BY mood",
                (date_from,))
            out = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for r in cur.fetchall():
                out[int(r["mood"])] = int(r["c"])
            return out
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"days": days})
            return {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    def count(self) -> int:
        """Total number of journal entries."""
        try:
            cur = db.get_conn().execute(
                "SELECT COUNT(*) AS c FROM journal_entries")
            row = cur.fetchone()
            return int(row["c"]) if row else 0
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

    def upsert(self, entry: JournalEntry) -> int:
        """Insert or update by date.  Returns the entry id."""
        existing = self.get_by_date(entry.date_iso)
        if existing is None:
            return self.add(entry)
        # Merge: fill in only the fields the caller provided.
        fields: Dict[str, Any] = {}
        for f in ("mood", "energy", "title", "body", "tags",
                  "gratitudes", "improvements"):
            v = getattr(entry, f, None)
            if v is not None and v != []:
                fields[f] = v
        if not fields:
            return existing.id or 0
        updated = self.update(existing.id or 0, **fields)
        return (updated.id if updated else 0) or 0

    # ------------------------------------------------------------------
    # Rich aggregations for charts / dashboards
    # ------------------------------------------------------------------

    def for_month(self, year: int, month: int) -> List[JournalEntry]:
        """Return all entries for a given (Gregorian) year/month."""
        try:
            first = date(year, month, 1)
            if month == 12:
                last = date(year, 12, 31)
            else:
                last = date(year, month + 1, 1) - timedelta(days=1)
            return self.list(date_from=first.isoformat(),
                              date_to=last.isoformat())
        except ValueError:
            return []

    def mood_energy_correlation(self, days: int = 30) -> float:
        """Pearson correlation between mood and energy (-1..1).

        Returns 0.0 if there are fewer than 3 paired entries.
        """
        date_from = add_days(today_iso(), -(days - 1))
        try:
            cur = db.get_conn().execute(
                "SELECT mood, energy FROM journal_entries "
                "WHERE mood IS NOT NULL AND energy IS NOT NULL "
                "AND date_iso >= ?",
                (date_from,))
            pairs = [(int(r["mood"]), int(r["energy"])) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"days": days})
            return 0.0
        if len(pairs) < 3:
            return 0.0
        n = len(pairs)
        sum_m = sum(p[0] for p in pairs)
        sum_e = sum(p[1] for p in pairs)
        sum_mm = sum(p[0] * p[0] for p in pairs)
        sum_ee = sum(p[1] * p[1] for p in pairs)
        sum_me = sum(p[0] * p[1] for p in pairs)
        num = n * sum_me - sum_m * sum_e
        denom = math.sqrt((n * sum_mm - sum_m * sum_m) *
                            (n * sum_ee - sum_e * sum_e))
        if denom == 0:
            return 0.0
        return round(num / denom, 3)

    def top_tags(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """Return ``[{tag, count}]`` for the most-used tags in the last `days` days."""
        date_from = add_days(today_iso(), -(days - 1))
        try:
            entries = self.list(date_from=date_from, date_to=today_iso())
        except Exception:  # noqa: BLE001
            return []
        counter: Dict[str, int] = {}
        for e in entries:
            for t in e.tags:
                counter[t] = counter.get(t, 0) + 1
        sorted_tags = sorted(counter.items(), key=lambda x: x[1], reverse=True)
        return [{"tag": t, "count": c} for t, c in sorted_tags[:limit]]

    def top_gratitudes(self, days: int = 90) -> List[str]:
        """Return the most-common gratitude entries (heuristic: any string
        appearing in >1 entry)."""
        date_from = add_days(today_iso(), -(days - 1))
        try:
            entries = self.list(date_from=date_from, date_to=today_iso())
        except Exception:  # noqa: BLE001
            return []
        counter: Dict[str, int] = {}
        for e in entries:
            for g in e.gratitudes:
                g_norm = (g or "").strip().lower()
                if g_norm:
                    counter[g_norm] = counter.get(g_norm, 0) + 1
        return [g for g, c in sorted(counter.items(),
                                       key=lambda x: x[1], reverse=True)
                if c > 1][:20]

    def summary(self, days: int = 30) -> Dict[str, Any]:
        """Return a one-shot summary dict for the Insights screen."""
        return {
            "count": self.count(),
            "average_mood": self.average_mood(days),
            "average_energy": self.average_energy(days),
            "mood_distribution": self.mood_distribution(days),
            "streak": self.streak(),
            "best_streak": self.best_streak(),
            "mood_energy_correlation": self.mood_energy_correlation(days),
            "top_tags": self.top_tags(days, limit=5),
            "has_entry_today": self.get_by_date(today_iso()) is not None,
        }


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

journal_service: JournalService = JournalService()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== journal self-tests ===")
    try:
        # Clean up any prior test entry
        existing = journal_service.get_by_date("2020-01-01")
        if existing:
            journal_service.delete(existing.id or 0)
        e = JournalEntry(
            date_iso="2020-01-01",
            mood=4,
            energy=3,
            title="Test",
            body="Body text",
            tags=["test", "journal"],
            gratitudes=["family", "health"],
            improvements=["sleep more"],
        )
        new_id = journal_service.add(e)
        assert new_id > 0, "add returned 0"
        got = journal_service.get(new_id)
        assert got is not None and got.title == "Test"
        assert got.tags == ["test", "journal"]
        assert got.gratitudes == ["family", "health"]
        # Update
        journal_service.update(new_id, mood=5, body="Updated body")
        got = journal_service.get(new_id)
        assert got is not None and got.mood == 5 and got.body == "Updated body"
        # Cleanup
        journal_service.delete(new_id)
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
