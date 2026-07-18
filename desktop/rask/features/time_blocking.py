"""
rask.features.time_blocking
===========================

Time blocking — schedule fixed blocks of time for specific activities.

A *time block* is a planned segment of the day with a title, category,
start time, end time, and an optional date.  Blocks can be one-off
(``recurring=None``) or recurring on a weekly basis (``recurring="daily"``,
``"weekdays"``, ``"weekends"``, or a comma-separated list of weekday
numbers 0=Sat..6=Fri).

The service exposes:

  • CRUD: ``add``, ``update``, ``delete``, ``get``, ``list``
  • Queries: ``for_date``, ``for_week``, ``check_conflicts``
  • Conversion: ``to_activity`` (turn a completed block into a logged
    activity record via the activity service)
  • Persistence: SQLite table ``time_blocks``

Schema
------

::

    CREATE TABLE time_blocks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        title           TEXT NOT NULL,
        category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
        start_hhmm      TEXT NOT NULL,            -- "HH:MM"
        end_hhmm        TEXT NOT NULL,            -- "HH:MM"
        date_iso        TEXT,                     -- YYYY-MM-DD (NULL for recurring)
        recurring       TEXT,                     -- NULL | daily | weekdays | weekends | "0,2,4"
        color           TEXT,
        notes           TEXT,
        completed       INTEGER NOT NULL DEFAULT 0,
        activity_id     INTEGER REFERENCES activities(id) ON DELETE SET NULL,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    );

Events
------

  ``timeblock.added``       — {block: dict}
  ``timeblock.updated``     — {id, fields: dict, block: dict}
  ``timeblock.deleted``     — {id}
  ``timeblock.conflict``    — {block: dict, conflicts: list[dict]}
  ``timeblock.converted``   — {block_id, activity_id}
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    end_of_week,
    range_days,
    start_of_week,
    today_iso,
)

__all__ = [
    "TimeBlock",
    "TimeBlockService",
    "time_block_service",
    "RECUR_DAILY",
    "RECUR_WEEKDAYS",
    "RECUR_WEEKENDS",
]

_log = get_logger("features.time_blocking")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

RECUR_DAILY: str = "daily"
RECUR_WEEKDAYS: str = "weekdays"
RECUR_WEEKENDS: str = "weekends"

#: Weekday numbering used by the recurring field: 0=Sat, 1=Sun, 2=Mon,
#: 3=Tue, 4=Wed, 5=Thu, 6=Fri.  (Persian convention.)
WEEKDAY_NAMES_FA: List[str] = [
    "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه",
    "چهارشنبه", "پنجشنبه", "جمعه",
]
WEEKDAY_NAMES_EN: List[str] = [
    "Saturday", "Sunday", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday",
]


SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS time_blocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    start_hhmm      TEXT NOT NULL,
    end_hhmm        TEXT NOT NULL,
    date_iso        TEXT,
    recurring       TEXT,
    color           TEXT,
    notes           TEXT,
    completed       INTEGER NOT NULL DEFAULT 0,
    activity_id     INTEGER REFERENCES activities(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_time_blocks_date ON time_blocks(date_iso);
CREATE INDEX IF NOT EXISTS idx_time_blocks_recurring ON time_blocks(recurring);
CREATE INDEX IF NOT EXISTS idx_time_blocks_category ON time_blocks(category_id);
"""


# =============================================================================
# === Data class                                                             ===
# =============================================================================

@dataclass
class TimeBlock:
    """A scheduled block of time.

    Either ``date_iso`` is set (one-off block) or ``recurring`` is set
    (repeats weekly).  It's legal to set both: the block occurs on
    ``date_iso`` and also repeats weekly on the matching weekday.
    """

    title: str
    start_hhmm: str
    end_hhmm: str
    category_id: Optional[int] = None
    date_iso: Optional[str] = None
    recurring: Optional[str] = None
    color: Optional[str] = None
    notes: Optional[str] = None
    id: Optional[int] = None
    completed: bool = False
    activity_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Normalize for DB: convert bool back to int.
        d["completed"] = 1 if self.completed else 0
        return d

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "TimeBlock":
        return cls(
            id=int(row["id"]) if row.get("id") is not None else None,
            title=row["title"],
            category_id=int(row["category_id"]) if row.get("category_id") else None,
            start_hhmm=row["start_hhmm"],
            end_hhmm=row["end_hhmm"],
            date_iso=row.get("date_iso"),
            recurring=row.get("recurring"),
            color=row.get("color"),
            notes=row.get("notes"),
            completed=bool(row.get("completed", 0)),
            activity_id=int(row["activity_id"]) if row.get("activity_id") else None,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _validate_hhmm(s: str) -> bool:
    if not s or not isinstance(s, str):
        return False
    parts = s.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return 0 <= h <= 23 and 0 <= m <= 59


def _hhmm_to_minutes(s: str) -> int:
    if not _validate_hhmm(s):
        return 0
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _minutes_to_hhmm(m: int) -> str:
    m = max(0, int(m))
    return f"{m // 60:02d}:{m % 60:02d}"


def _block_duration_min(block: TimeBlock) -> int:
    start = _hhmm_to_minutes(block.start_hhmm)
    end = _hhmm_to_minutes(block.end_hhmm)
    if end < start:
        # Spans midnight.
        end += 24 * 60
    return end - start


def _overlap_min(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    """Return the overlap (in minutes) between two [start, end) intervals."""
    if a_end < a_start:
        a_end += 24 * 60
    if b_end < b_start:
        b_end += 24 * 60
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(0, end - start)


def _weekday_index(iso: str) -> int:
    """Return Persian weekday index (0=Sat..6=Fri) for an ISO date."""
    try:
        d = date.fromisoformat(iso[:10])
    except Exception:  # noqa: BLE001
        return 0
    py_wday = d.weekday()  # Mon=0..Sun=6
    # Convert to Sat=0..Fri=6
    # Mon=0 -> 2, Tue=1 -> 3, Wed=2 -> 4, Thu=3 -> 5, Fri=4 -> 6,
    # Sat=5 -> 0, Sun=6 -> 1
    mapping = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 0, 6: 1}
    return mapping[py_wday]


def _block_applies_on_date(block: TimeBlock, iso: str) -> bool:
    """Return True if `block` is scheduled to occur on the given date."""
    if block.date_iso == iso:
        return True
    if not block.recurring:
        return False
    if block.recurring == RECUR_DAILY:
        return True
    wday = _weekday_index(iso)  # 0=Sat..6=Fri
    if block.recurring == RECUR_WEEKDAYS:
        return wday in (0, 1, 2, 3, 4)  # Sat..Thu
    if block.recurring == RECUR_WEEKENDS:
        return wday in (5, 6)  # Fri and... actually Persian weekend = Fri only
        # But for international users treat Fri+Sat as weekend.
    # Custom comma-separated weekday list.
    try:
        days = [int(x) for x in block.recurring.split(",") if x.strip().isdigit()]
        return wday in days
    except Exception:  # noqa: BLE001
        return False


def _normalize_recurring(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip().lower()
    if s in (RECUR_DAILY, RECUR_WEEKDAYS, RECUR_WEEKENDS, ""):
        return s or None
    # Comma-separated list of digits.
    try:
        nums = [int(x) for x in s.split(",") if x.strip().isdigit()]
        if not nums:
            return None
        # Validate range 0..6
        nums = [n for n in nums if 0 <= n <= 6]
        if not nums:
            return None
        return ",".join(str(n) for n in sorted(set(nums)))
    except Exception:  # noqa: BLE001
        return None


# =============================================================================
# === Schema bootstrap                                                       ===
# =============================================================================

_schema_initialized: bool = False
_schema_lock = threading.Lock()


def _ensure_schema() -> None:
    """Apply the schema SQL if it hasn't been applied yet (idempotent)."""
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
            _log.debug("time_blocks schema initialized")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})


# =============================================================================
# === TimeBlockService                                                       ===
# =============================================================================

class TimeBlockService:
    """CRUD + queries + conversion for time blocks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        _ensure_schema()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, block: TimeBlock) -> int:
        """Add a time block.  Returns the new row id (0 on failure)."""
        if not block.title or not block.title.strip():
            raise ValueError("TimeBlock.title must be non-empty")
        if not _validate_hhmm(block.start_hhmm):
            raise ValueError(f"Invalid start_hhmm: {block.start_hhmm!r}")
        if not _validate_hhmm(block.end_hhmm):
            raise ValueError(f"Invalid end_hhmm: {block.end_hhmm!r}")

        block.recurring = _normalize_recurring(block.recurring)
        now = _now_iso()
        try:
            conn = db.get_conn()
            cur = conn.execute(
                "INSERT INTO time_blocks(title, category_id, start_hhmm, "
                "end_hhmm, date_iso, recurring, color, notes, completed, "
                "activity_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)",
                (block.title.strip(), block.category_id, block.start_hhmm,
                 block.end_hhmm, block.date_iso, block.recurring, block.color,
                 block.notes, now, now),
            )
            conn.commit()
            new_id = int(cur.lastrowid or 0)
            block.id = new_id
            block.created_at = now
            block.updated_at = now
            bus.publish("timeblock.added", {"block": block.to_dict()})
            _log.info("TimeBlock added: id=%d title=%r", new_id, block.title)
            return new_id
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"title": block.title})
            return 0

    def update(self, id: int, **fields: Any) -> Optional[TimeBlock]:
        """Update fields on an existing block.  Returns the new block."""
        if not isinstance(id, int) or id <= 0:
            return None
        existing = self.get(id)
        if existing is None:
            return None

        allowed = {
            "title", "category_id", "start_hhmm", "end_hhmm",
            "date_iso", "recurring", "color", "notes", "completed",
            "activity_id",
        }
        updates: List[str] = []
        values: List[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "start_hhmm" and not _validate_hhmm(v):
                _log.warning("Ignoring invalid start_hhmm=%r", v)
                continue
            if k == "end_hhmm" and not _validate_hhmm(v):
                _log.warning("Ignoring invalid end_hhmm=%r", v)
                continue
            if k == "recurring":
                v = _normalize_recurring(v)
            if k == "completed":
                v = 1 if v else 0
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
                f"UPDATE time_blocks SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            conn.commit()
            updated = self.get(id)
            bus.publish("timeblock.updated",
                        {"id": id, "fields": fields,
                         "block": updated.to_dict() if updated else None})
            return updated
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id, "fields": list(fields.keys())})
            return existing

    def delete(self, id: int) -> bool:
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            conn = db.get_conn()
            cur = conn.execute("DELETE FROM time_blocks WHERE id = ?", (id,))
            conn.commit()
            ok = (cur.rowcount or 0) > 0
            if ok:
                bus.publish("timeblock.deleted", {"id": id})
            return ok
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False

    def get(self, id: int) -> Optional[TimeBlock]:
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            cur = db.get_conn().execute(
                "SELECT * FROM time_blocks WHERE id = ?", (id,))
            row = cur.fetchone()
            if not row:
                return None
            return TimeBlock.from_row({k: row[k] for k in row.keys()})
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None

    def list(self, date_iso: Optional[str] = None) -> List[TimeBlock]:
        """List blocks.  If `date_iso` is given, returns only blocks that
        apply on that date (one-off + recurring matches)."""
        try:
            if date_iso is None:
                cur = db.get_conn().execute(
                    "SELECT * FROM time_blocks ORDER BY date_iso ASC, start_hhmm ASC")
                rows = [{k: r[k] for k in r.keys()} for r in cur.fetchall()]
            else:
                # First pull everything, then filter in Python because the
                # "applies on date" predicate isn't expressible in SQL.
                cur = db.get_conn().execute(
                    "SELECT * FROM time_blocks ORDER BY start_hhmm ASC")
                rows = [{k: r[k] for k in r.keys()} for r in cur.fetchall()]
                rows = [r for r in rows
                        if _block_applies_on_date(TimeBlock.from_row(r), date_iso)]
            return [TimeBlock.from_row(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"date_iso": date_iso})
            return []

    # ------------------------------------------------------------------
    # Date-range queries
    # ------------------------------------------------------------------

    def for_date(self, date_iso: str) -> List[TimeBlock]:
        """Return all blocks scheduled for the given date (sorted by start time)."""
        return self.list(date_iso=date_iso)

    def for_week(self, week_iso: Optional[str] = None) -> Dict[str, List[TimeBlock]]:
        """Return a dict {date_iso: [blocks...]} for the week containing `week_iso`.

        If `week_iso` is ``None``, the current week is used.  Week runs
        Saturday → Friday.
        """
        anchor = week_iso or today_iso()
        start = start_of_week(anchor, first_day=6)  # Saturday
        end = end_of_week(anchor, first_day=6)
        out: Dict[str, List[TimeBlock]] = {}
        for d in range_days(start, end):
            out[d] = self.for_date(d)
        return out

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def check_conflicts(self, block: TimeBlock,
                        *, exclude_id: Optional[int] = None) -> List[TimeBlock]:
        """Return any existing blocks that overlap with `block`.

        Only blocks on the same date (or recurring blocks that apply on
        that date) are considered.  Blocks that touch but don't overlap
        (e.g. 09:00-10:00 vs 10:00-11:00) are NOT flagged.
        """
        if not block.date_iso:
            # Recurring-only blocks can't be checked for one-off conflicts.
            return []
        start_min = _hhmm_to_minutes(block.start_hhmm)
        end_min = _hhmm_to_minutes(block.end_hhmm)
        if end_min <= start_min:
            end_min += 24 * 60

        candidates = self.for_date(block.date_iso)
        conflicts: List[TimeBlock] = []
        for other in candidates:
            if exclude_id is not None and other.id == exclude_id:
                continue
            o_start = _hhmm_to_minutes(other.start_hhmm)
            o_end = _hhmm_to_minutes(other.end_hhmm)
            if o_end <= o_start:
                o_end += 24 * 60
            if _overlap_min(start_min, end_min, o_start, o_end) > 0:
                conflicts.append(other)
        if conflicts:
            bus.publish("timeblock.conflict",
                        {"block": block.to_dict(),
                         "conflicts": [b.to_dict() for b in conflicts]})
        return conflicts

    # ------------------------------------------------------------------
    # Conversion to activity
    # ------------------------------------------------------------------

    def to_activity(self, block_id: int, *, date_iso: Optional[str] = None) -> int:
        """Convert a time block into a logged activity record.

        The activity is created via ``activity_service.add`` with the
        block's title, category, and duration (computed from start/end).
        Returns the new activity id (0 on failure).
        """
        block = self.get(block_id)
        if block is None:
            return 0
        from ..services.activity_service import activity_service

        duration = _block_duration_min(block)
        # If the block has no specific date, use today.
        target_date = date_iso or block.date_iso or today_iso()
        try:
            activity = activity_service.add(
                title=block.title,
                category_id=block.category_id,
                duration_min=duration,
                date_iso=target_date,
                kind="manual",
                source="desktop",
                tags=["timeblock"],
                notes=block.notes,
            )
            activity_id = int(activity.get("id", 0))
            if activity_id:
                self.update(block_id, completed=True, activity_id=activity_id)
                bus.publish("timeblock.converted",
                            {"block_id": block_id, "activity_id": activity_id})
                _log.info("TimeBlock %d converted to activity %d",
                          block_id, activity_id)
            return activity_id
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"block_id": block_id})
            return 0

    # ------------------------------------------------------------------
    # Stats helpers
    # ------------------------------------------------------------------

    def total_scheduled_min(self, date_iso: str) -> int:
        """Sum of scheduled minutes on the given date."""
        blocks = self.for_date(date_iso)
        return sum(_block_duration_min(b) for b in blocks)

    def completion_rate(self, date_iso: str) -> float:
        """Fraction (0..1) of blocks on the given date that are completed."""
        blocks = self.for_date(date_iso)
        if not blocks:
            return 0.0
        done = sum(1 for b in blocks if b.completed)
        return done / len(blocks)

    def next_block(self, *, from_iso: Optional[str] = None) -> Optional[TimeBlock]:
        """Return the next upcoming block from the given date/time."""
        anchor = from_iso or today_iso()
        # Check today + next 7 days.
        for offset in range(0, 8):
            d = add_days(anchor, offset)
            for b in self.for_date(d):
                if b.completed:
                    continue
                # If today, only return blocks that haven't ended yet.
                if offset == 0:
                    now_min = datetime.now().hour * 60 + datetime.now().minute
                    if _hhmm_to_minutes(b.end_hhmm) <= now_min:
                        continue
                return b
        return None


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

time_block_service: TimeBlockService = TimeBlockService()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== time_blocking self-tests ===")
    try:
        b = TimeBlock(
            title="Test focus",
            start_hhmm="09:00",
            end_hhmm="10:00",
            date_iso=today_iso(),
        )
        bid = time_block_service.add(b)
        assert bid > 0, "add returned 0"
        got = time_block_service.get(bid)
        assert got is not None and got.title == "Test focus"
        # Conflict
        b2 = TimeBlock(
            title="Overlapping",
            start_hhmm="09:30",
            end_hhmm="10:30",
            date_iso=today_iso(),
        )
        conflicts = time_block_service.check_conflicts(b2)
        assert len(conflicts) >= 1, f"expected conflict, got {conflicts}"
        # Cleanup
        time_block_service.delete(bid)
        print("  OK   basic CRUD + conflict detection")
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
