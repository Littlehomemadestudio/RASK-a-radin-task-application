"""
rask.utils.migrations
=====================

Lightweight SQLite migration framework for the Rask database.

Each :class:`Migration` is a triple of (version, description, up, down).
The :class:`MigrationRunner` applies pending migrations in order,
records each in the ``changelog`` table, and supports rollback to a
previous version.

Pre-defined migrations
----------------------

  • ``MIGRATION_V1_TO_V2``  — add ``journal_entries`` table
  • ``MIGRATION_V2_TO_V3``  — add ``habits`` + ``habit_logs`` tables
  • ``MIGRATION_V3_TO_V4``  — add ``mood_entries`` table
  • ``MIGRATION_V4_TO_V5``  — add ``time_blocks`` table

Note: these mirror what :mod:`rask.features.journal`, :mod:`rask.features.habits`,
:mod:`rask.features.mood_tracker`, and :mod:`rask.features.time_blocking` already
create on-demand via their own ``_ensure_schema()`` functions — the
migrations here are provided for users who want explicit versioned
control over their schema.

Example
-------

    >>> from rask.utils.migrations import (
    ...     MigrationRunner, ALL_MIGRATIONS,
    ... )
    >>> runner = MigrationRunner()
    >>> runner.register_all(ALL_MIGRATIONS)
    >>> runner.run_pending()  # apply any not-yet-applied migrations
    4
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from .. import database as db
from ..core.logging_utils import get_logger

__all__ = [
    "Migration",
    "MigrationRunner",
    "MIGRATION_V1_TO_V2",
    "MIGRATION_V2_TO_V3",
    "MIGRATION_V3_TO_V4",
    "MIGRATION_V4_TO_V5",
    "ALL_MIGRATIONS",
]

_log = get_logger("utils.migrations")


# =============================================================================
# === Migration class                                                         ===
# =============================================================================

class Migration:
    """A single schema migration.

    Parameters
    ----------
    version
        Target schema version after this migration runs (must be > 0).
    description
        Human-readable summary.
    up
        Callable that takes a ``sqlite3.Connection`` and applies the
        forward migration.
    down
        Optional callable that reverses the migration.
    """

    def __init__(
        self,
        version: int,
        description: str,
        up: Callable[[Any], None],
        down: Optional[Callable[[Any], None]] = None,
    ) -> None:
        if not isinstance(version, int) or version <= 0:
            raise ValueError(f"version must be a positive int, got {version!r}")
        if not description:
            raise ValueError("description must be non-empty")
        if not callable(up):
            raise TypeError("up must be callable")
        self.version: int = version
        self.description: str = description
        self.up: Callable[[Any], None] = up
        self.down: Optional[Callable[[Any], None]] = down

    def __repr__(self) -> str:
        return (f"<Migration v{self.version}: {self.description}>")

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Migration):
            return NotImplemented
        return self.version == other.version

    def __hash__(self) -> int:
        return hash(self.version)


# =============================================================================
# === Pre-defined migrations                                                 ===
# =============================================================================

MIGRATION_V1_TO_V2: Migration = Migration(
    version=2,
    description="Add journal_entries table",
    up=lambda conn: conn.executescript("""
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
    """),
    down=lambda conn: conn.executescript(
        "DROP TABLE IF EXISTS journal_entries;"
    ),
)


MIGRATION_V2_TO_V3: Migration = Migration(
    version=3,
    description="Add habits and habit_logs tables",
    up=lambda conn: conn.executescript("""
        CREATE TABLE IF NOT EXISTS habits (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            description     TEXT,
            color           TEXT,
            icon            TEXT,
            frequency       TEXT NOT NULL,
            target_count    INTEGER NOT NULL DEFAULT 1,
            active          INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS habit_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id        INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
            date_iso        TEXT NOT NULL,
            completed       INTEGER NOT NULL DEFAULT 1,
            count           INTEGER NOT NULL DEFAULT 1,
            note            TEXT,
            created_at      TEXT NOT NULL,
            UNIQUE(habit_id, date_iso)
        );
        CREATE INDEX IF NOT EXISTS idx_habit_logs_habit ON habit_logs(habit_id);
        CREATE INDEX IF NOT EXISTS idx_habit_logs_date ON habit_logs(date_iso);
    """),
    down=lambda conn: conn.executescript(
        "DROP TABLE IF EXISTS habit_logs; DROP TABLE IF EXISTS habits;"
    ),
)


MIGRATION_V3_TO_V4: Migration = Migration(
    version=4,
    description="Add mood_entries table",
    up=lambda conn: conn.executescript("""
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
        CREATE INDEX IF NOT EXISTS idx_mood_entries_date ON mood_entries(date_iso);
        CREATE INDEX IF NOT EXISTS idx_mood_entries_mood ON mood_entries(mood);
    """),
    down=lambda conn: conn.executescript(
        "DROP TABLE IF EXISTS mood_entries;"
    ),
)


MIGRATION_V4_TO_V5: Migration = Migration(
    version=5,
    description="Add time_blocks table",
    up=lambda conn: conn.executescript("""
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
    """),
    down=lambda conn: conn.executescript(
        "DROP TABLE IF EXISTS time_blocks;"
    ),
)


#: All pre-defined migrations, ordered by version.
ALL_MIGRATIONS: List[Migration] = [
    MIGRATION_V1_TO_V2,
    MIGRATION_V2_TO_V3,
    MIGRATION_V3_TO_V4,
    MIGRATION_V4_TO_V5,
]


# =============================================================================
# === MigrationRunner                                                        ===
# =============================================================================

class MigrationRunner:
    """Apply / rollback migrations on the current Rask DB."""

    def __init__(self) -> None:
        self._migrations: Dict[int, Migration] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, migration: Migration) -> None:
        """Register a migration.  Replaces any with the same version."""
        if not isinstance(migration, Migration):
            raise TypeError("expected Migration instance")
        self._migrations[migration.version] = migration

    def register_all(self, migrations: Sequence[Migration]) -> None:
        """Register a sequence of migrations."""
        for m in migrations:
            self.register(m)

    def unregister(self, version: int) -> bool:
        """Remove a migration from the registry.  Returns True if found."""
        return self._migrations.pop(version, None) is not None

    def registered_versions(self) -> List[int]:
        """Return sorted list of registered migration versions."""
        return sorted(self._migrations.keys())

    # ------------------------------------------------------------------
    # DB version tracking
    # ------------------------------------------------------------------

    def current_version(self) -> int:
        """Return the highest applied schema version (0 if none)."""
        try:
            conn = db.get_conn()
            cur = conn.execute(
                "SELECT MAX(version) AS v FROM changelog"
            )
            row = cur.fetchone()
            if not row or row["v"] is None:
                return 0
            return int(row["v"])
        except Exception as exc:  # noqa: BLE001
            _log.error("current_version failed: %s", exc)
            return 0

    def applied_versions(self) -> List[int]:
        """Return all applied versions, sorted ascending."""
        try:
            conn = db.get_conn()
            cur = conn.execute(
                "SELECT version FROM changelog ORDER BY version ASC"
            )
            return [int(r["version"]) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            _log.error("applied_versions failed: %s", exc)
            return []

    def pending_versions(self) -> List[int]:
        """Return registered versions not yet applied, sorted ascending."""
        current = self.current_version()
        return [v for v in self.registered_versions() if v > current]

    # ------------------------------------------------------------------
    # Apply / rollback
    # ------------------------------------------------------------------

    def run_pending(self) -> int:
        """Apply all pending migrations.  Returns count applied."""
        pending = self.pending_versions()
        if not pending:
            _log.debug("No pending migrations")
            return 0

        conn = db.get_conn()
        applied = 0
        for v in pending:
            m = self._migrations[v]
            try:
                _log.info("Applying migration v%d: %s", v, m.description)
                m.up(conn)
                self._record_applied(v, m.description)
                conn.commit()
                applied += 1
            except Exception as exc:  # noqa: BLE001
                _log.error("Migration v%d failed: %s", v, exc)
                conn.rollback()
                raise
        _log.info("Applied %d migrations (now at v%d)",
                  applied, self.current_version())
        return applied

    def rollback(self, to_version: int = 0) -> int:
        """Roll back to `to_version`.  Returns count rolled back.

        Walks applied versions in descending order, calling each
        migration's ``down`` (if defined).  Migrations without a
        ``down`` callback are skipped (their changelog entry is still
        removed, but the schema change is left in place).
        """
        current = self.current_version()
        if to_version >= current:
            return 0
        applied = sorted(self.applied_versions(), reverse=True)
        to_rollback = [v for v in applied if v > to_version]
        if not to_rollback:
            return 0

        conn = db.get_conn()
        rolled = 0
        for v in to_rollback:
            m = self._migrations.get(v)
            try:
                if m and m.down:
                    _log.info("Rolling back migration v%d", v)
                    m.down(conn)
                else:
                    _log.warning(
                        "Migration v%d has no down() — skipping schema change",
                        v,
                    )
                self._record_rolled_back(v)
                conn.commit()
                rolled += 1
            except Exception as exc:  # noqa: BLE001
                _log.error("Rollback v%d failed: %s", v, exc)
                conn.rollback()
                raise
        return rolled

    def reset(self) -> int:
        """Roll back ALL applied migrations.  Returns count rolled back."""
        return self.rollback(to_version=0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_applied(self, version: int, description: str) -> None:
        """Record an applied migration in the changelog table."""
        conn = db.get_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO changelog(version, applied_at, description) "
            "VALUES (?, ?, ?)",
            (version, now, description),
        )

    def _record_rolled_back(self, version: int) -> None:
        """Remove a migration from the changelog table."""
        conn = db.get_conn()
        conn.execute(
            "DELETE FROM changelog WHERE version = ?",
            (version,),
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return a status dict with current / pending / applied info."""
        return {
            "current_version": self.current_version(),
            "applied_versions": self.applied_versions(),
            "registered_versions": self.registered_versions(),
            "pending_versions": self.pending_versions(),
            "pending_count": len(self.pending_versions()),
        }

    def print_status(self) -> None:
        """Pretty-print the migration status to stdout."""
        s = self.status()
        print(f"Current version: v{s['current_version']}")
        print(f"Applied: {s['applied_versions']}")
        print(f"Registered: {s['registered_versions']}")
        print(f"Pending: {s['pending_versions']}")
        if s["pending_versions"]:
            print(f"\n{len(s['pending_versions'])} migrations to apply:")
            for v in s["pending_versions"]:
                m = self._migrations[v]
                print(f"  v{v}: {m.description}")
        else:
            print("\nAll migrations applied — DB is up to date.")


# =============================================================================
# === Module-level convenience                                                ===
# =============================================================================

def run_all_pending() -> int:
    """Register all built-in migrations and apply any pending.

    Convenience function for use in startup scripts::

        from rask.utils.migrations import run_all_pending
        run_all_pending()
    """
    runner = MigrationRunner()
    runner.register_all(ALL_MIGRATIONS)
    return runner.run_pending()


if __name__ == "__main__":
    # CLI entry: print status and apply pending.
    runner = MigrationRunner()
    runner.register_all(ALL_MIGRATIONS)
    runner.print_status()
    print()
    n = runner.run_pending()
    print(f"Applied {n} migrations.")
