"""
rask.features.focus_mode
========================

Deep-focus mode: a single-button "I want to focus now" feature that
blocks distractions for a chosen duration and logs a focus session as
an activity when complete.

Distinct from :mod:`rask.features.pomodoro` (which cycles work/break),
focus mode is one continuous block of deep work.  Use cases:

  • "Deep Focus: 50 minutes — write the report"
  • "No phone, no internet — just code"

Features:

  • Configurable duration (default 50 min)
  • Optional "block internet" (modifies ``/etc/hosts`` on Linux/macOS,
    requires admin/root — falls back to a note in the kv store if
    permissions are missing)
  • Optional "block apps" (list of process names — on Windows we kill
    matching processes; on Linux/macOS we pkill them)
  • Live "remaining time" + "interruption count" display
  • On end: creates an activity with ``kind="focus"``, tags
    ``["focus", "deep_work"]``, and notes containing focus metadata

Schema
------

Uses the existing ``sessions`` table for focus-session metadata
(state, planned_min, actual_min, pause_count, pause_total_sec,
metadata_json) and the ``activities`` table for the final activity
record.

Events
------

  ``focus.started``        — {session_id, duration_min, title, block_internet}
  ``focus.paused``         — {session_id, at_iso}
  ``focus.resumed``        — {session_id, at_iso, remaining_sec}
  ``focus.interruption``   — {session_id, note, count}
  ``focus.ended``          — {session_id, activity_id, duration_min,
                              interruption_count, early}
  ``focus.tick``           — {session_id, remaining_sec}
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import now_iso_utc, today_iso

__all__ = [
    "FocusMode",
    "focus_mode",
    "FocusStats",
]

_log = get_logger("features.focus")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

#: Kv-store key for the active focus session id.
ACTIVE_KEY: str = "focus_mode.active_session_id"

#: Kv-store key for the focus session settings.
SETTINGS_KEY: str = "focus_mode.settings"

#: Default focus session length.
DEFAULT_DURATION_MIN: int = 50

#: Default title for focus sessions.
DEFAULT_TITLE: str = "Deep Focus"

#: Tags applied to focus-mode-generated activities.
FOCUS_TAGS: List[str] = ["focus", "deep_work"]


# =============================================================================
# === Data classes                                                           ===
# =============================================================================

@dataclass
class FocusSettings:
    """User-configurable focus-mode settings."""

    default_duration_min: int = DEFAULT_DURATION_MIN
    block_internet: bool = False
    block_apps: List[str] = field(default_factory=list)
    sound_on_complete: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "FocusSettings":
        if not d:
            return cls()
        return cls(
            default_duration_min=int(d.get("default_duration_min",
                                            DEFAULT_DURATION_MIN)),
            block_internet=bool(d.get("block_internet", False)),
            block_apps=list(d.get("block_apps", []) or []),
            sound_on_complete=bool(d.get("sound_on_complete", True)),
        )


@dataclass
class FocusStats:
    """Aggregate focus stats for a date range."""

    total_sessions: int = 0
    total_focus_min: int = 0
    avg_duration_min: float = 0.0
    interruption_count: int = 0
    early_end_count: int = 0
    complete_count: int = 0
    best_day_iso: Optional[str] = None
    best_day_min: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _add_minutes_iso(minutes: int) -> str:
    return (_now_dt() + timedelta(minutes=minutes)).isoformat()


def _seconds_until(ends_at: Optional[str]) -> int:
    if not ends_at:
        return 0
    end = _parse_iso(ends_at)
    if end is None:
        return 0
    return max(0, int((end - _now_dt()).total_seconds()))


def _is_admin() -> bool:
    """Return True if the current process has admin/root privileges."""
    if platform.system() == "Windows":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # noqa: BLE001
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _block_internet_hosts(domains: List[str]) -> bool:
    """Add domains to /etc/hosts pointing at 127.0.0.1.

    Returns True if the modification was made; False otherwise (e.g.
    no admin rights, on Windows, etc.).
    """
    if platform.system() == "Windows":
        return False  # Use a different mechanism on Windows (not implemented)
    if not _is_admin():
        _log.warning("block_internet: not running as admin — skipping hosts edit")
        return False
    hosts_path = "/etc/hosts"
    try:
        with open(hosts_path, "a", encoding="utf-8") as f:
            f.write("\n# Rask focus-mode block\n")
            for d in domains:
                f.write(f"127.0.0.1  {d}\n")
                f.write(f"127.0.0.1  www.{d}\n")
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("block_internet: hosts edit failed: %s", exc)
        return False


def _unblock_internet_hosts() -> bool:
    """Remove the Rask focus-mode block from /etc/hosts."""
    if platform.system() == "Windows":
        return False
    if not _is_admin():
        return False
    hosts_path = "/etc/hosts"
    try:
        with open(hosts_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        out: List[str] = []
        in_block = False
        for line in lines:
            if "# Rask focus-mode block" in line:
                in_block = True
                continue
            if in_block:
                if line.strip() == "" or line.startswith("127.0.0.1"):
                    continue
                in_block = False
            out.append(line)
        with open(hosts_path, "w", encoding="utf-8") as f:
            f.writelines(out)
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("unblock_internet: hosts edit failed: %s", exc)
        return False


def _kill_app(process_name: str) -> int:
    """Kill any running process whose name contains `process_name`.

    Returns the number of processes killed.  Best-effort: never raises.
    """
    if not process_name:
        return 0
    try:
        if platform.system() == "Windows":
            # taskkill /IM name.exe /F
            r = subprocess.run(
                ["taskkill", "/IM", process_name, "/F"],
                capture_output=True, text=True, timeout=5,
            )
            return 1 if r.returncode == 0 else 0
        # Unix-like: pkill -f
        r = subprocess.run(
            ["pkill", "-f", process_name],
            capture_output=True, timeout=5,
        )
        return 1 if r.returncode == 0 else 0
    except Exception as exc:  # noqa: BLE001
        _log.debug("kill_app %r failed: %s", process_name, exc)
        return 0


# =============================================================================
# === FocusMode                                                              ===
# =============================================================================

class FocusMode:
    """Deep focus mode.

    Module-level singleton :data:`focus_mode` is the instance to use.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings: FocusSettings = self._load_settings()
        self._session_id: Optional[int] = None
        self._ends_at: Optional[str] = None
        self._title: str = DEFAULT_TITLE
        self._interruption_count: int = 0
        self._paused: bool = False
        self._paused_remaining_sec: Optional[int] = None
        self._internet_blocked: bool = False
        self._restore_session_if_any()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self) -> FocusSettings:
        return FocusSettings(**self._settings.to_dict())

    def update_settings(self, **fields: Any) -> FocusSettings:
        with self._lock:
            for k, v in fields.items():
                if hasattr(self._settings, k):
                    setattr(self._settings, k, v)
            self._save_settings()
            return self.get_settings()

    def _load_settings(self) -> FocusSettings:
        try:
            return FocusSettings.from_dict(db.kv_get_json(SETTINGS_KEY, {}))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return FocusSettings()

    def _save_settings(self) -> None:
        try:
            db.kv_set_json(SETTINGS_KEY, self._settings.to_dict())
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, duration_min: Optional[int] = None,
              title: str = DEFAULT_TITLE,
              block_internet: Optional[bool] = None,
              block_apps: Optional[List[str]] = None) -> Dict[str, Any]:
        """Start a focus session.

        Parameters
        ----------
        duration_min : int, optional
            Defaults to ``settings.default_duration_min``.
        title : str
            Activity title for the eventual activity record.
        block_internet : bool, optional
            If True, modify ``/etc/hosts`` to block common distractor
            domains.  Falls back silently if no admin rights.
        block_apps : list[str], optional
            Process names to kill on start.
        """
        with self._lock:
            if self._session_id is not None:
                _log.warning("Focus already active — ending previous session first")
                self.end(early=True)

            duration = max(1, int(duration_min or self._settings.default_duration_min))
            if block_internet is None:
                block_internet = self._settings.block_internet
            if block_apps is None:
                block_apps = list(self._settings.block_apps)

            now = _now_ts()
            try:
                session_id = db.session_add(
                    planned_min=duration,
                    started_at=now,
                    activity_id=None,
                    metadata={
                        "title": title,
                        "block_internet": block_internet,
                        "block_apps": list(block_apps or []),
                        "interruptions": [],
                        "kind": "focus",
                    },
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return {}

            self._session_id = session_id
            self._ends_at = _add_minutes_iso(duration)
            self._title = title
            self._interruption_count = 0
            self._paused = False
            self._paused_remaining_sec = None

            # Apply blocking.
            if block_internet:
                distractor_domains = [
                    "twitter.com", "x.com", "instagram.com",
                    "facebook.com", "youtube.com", "reddit.com",
                    "tiktok.com", "netflix.com", "discord.com",
                    "twitch.tv", "pinterest.com",
                ]
                self._internet_blocked = _block_internet_hosts(distractor_domains)
            if block_apps:
                for name in block_apps:
                    _kill_app(name)

            db.kv_set_int(ACTIVE_KEY, session_id)

            payload = {
                "session_id": session_id,
                "duration_min": duration,
                "title": title,
                "ends_at": self._ends_at,
                "block_internet": block_internet,
                "block_apps": list(block_apps or []),
                "internet_blocked": self._internet_blocked,
            }
            bus.publish("focus.started", payload)
            _log.info("Focus session started: id=%d duration=%dm title=%r",
                      session_id, duration, title)
            return payload

    def end(self, early: bool = False) -> Dict[str, Any]:
        """End the active focus session.

        Creates an activity record via the activity service with the
        actual focus duration (or partial duration if ``early=True``).

        Returns a dict with ``activity_id`` and stats.
        """
        with self._lock:
            if self._session_id is None:
                return {}

            session_id = self._session_id
            ends_at = self._ends_at
            title = self._title
            interruptions = self._interruption_count

            # Compute actual focus minutes.
            session = db.session_get(session_id) or {}
            started_at = session.get("started_at") or _now_ts()
            try:
                start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                elapsed_sec = (_now_dt() - start_dt).total_seconds()
                actual_min = max(0, int(elapsed_sec // 60))
            except Exception:  # noqa: BLE001
                actual_min = 0

            # Update session row.
            db.session_update(
                session_id,
                actual_min=actual_min,
                ended_at=_now_ts(),
                state="completed" if not early else "abandoned",
                pause_count=0,
                pause_total_sec=0,
            )

            # Log activity (only if at least 1 minute elapsed).
            activity_id = 0
            if actual_min >= 1:
                try:
                    from ..services.activity_service import activity_service
                    activity = activity_service.add(
                        title=title or "Deep Focus",
                        duration_min=actual_min,
                        date_iso=today_iso(),
                        kind="manual",
                        source="desktop",
                        tags=FOCUS_TAGS,
                        notes=f"Focus session (interruptions: {interruptions})",
                    )
                    activity_id = int(activity.get("id", 0))
                    # Link activity to session.
                    db.session_update(session_id, activity_id=activity_id)
                except Exception as exc:  # noqa: BLE001
                    log_exception(_log, exc, {})

            # Restore internet if we blocked it.
            if self._internet_blocked:
                _unblock_internet_hosts()
                self._internet_blocked = False

            # Clear state.
            self._session_id = None
            self._ends_at = None
            self._title = DEFAULT_TITLE
            self._interruption_count = 0
            self._paused = False
            self._paused_remaining_sec = None
            db.kv_set(ACTIVE_KEY, "")

            payload = {
                "session_id": session_id,
                "activity_id": activity_id,
                "duration_min": actual_min,
                "interruption_count": interruptions,
                "early": early,
            }
            bus.publish("focus.ended", payload)
            _log.info("Focus session ended: id=%d min=%d early=%s",
                      session_id, actual_min, early)
            return payload

    def is_active(self) -> bool:
        return self._session_id is not None

    def is_paused(self) -> bool:
        return self._paused

    def remaining_sec(self) -> int:
        if not self.is_active():
            return 0
        if self._paused and self._paused_remaining_sec is not None:
            return int(self._paused_remaining_sec)
        return _seconds_until(self._ends_at)

    def interruption_count(self) -> int:
        return self._interruption_count

    def add_interruption(self, note: Optional[str] = None) -> int:
        """Log an interruption.  Returns the new count."""
        with self._lock:
            if self._session_id is None:
                return 0
            self._interruption_count += 1
            # Persist into session metadata.
            try:
                session = db.session_get(self._session_id) or {}
                meta = session.get("metadata", {}) or {}
                interruptions = list(meta.get("interruptions", []))
                interruptions.append({
                    "n": self._interruption_count,
                    "at_iso": _now_ts(),
                    "note": note,
                })
                meta["interruptions"] = interruptions
                db.session_update(self._session_id, metadata=meta)
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
            payload = {
                "session_id": self._session_id,
                "note": note,
                "count": self._interruption_count,
            }
            bus.publish("focus.interruption", payload)
            _log.info("Focus interruption #%d: %s",
                      self._interruption_count, note or "(no note)")
            return self._interruption_count

    def pause(self) -> Dict[str, Any]:
        with self._lock:
            if self._session_id is None or self._paused:
                return {}
            self._paused = True
            self._paused_remaining_sec = self.remaining_sec()
            payload = {"session_id": self._session_id, "at_iso": _now_ts()}
            bus.publish("focus.paused", payload)
            return payload

    def resume(self) -> Dict[str, Any]:
        with self._lock:
            if self._session_id is None or not self._paused:
                return {}
            remaining = int(self._paused_remaining_sec or 0)
            self._ends_at = (_now_dt() + timedelta(seconds=remaining)).isoformat()
            self._paused = False
            self._paused_remaining_sec = None
            payload = {"session_id": self._session_id,
                       "at_iso": _now_ts(),
                       "remaining_sec": remaining}
            bus.publish("focus.resumed", payload)
            return payload

    def tick(self) -> Optional[Dict[str, Any]]:
        """Called by UI driver every second.  Returns ``None`` if not active."""
        if not self.is_active() or self._paused:
            return None
        remaining = self.remaining_sec()
        if remaining <= 0:
            # Auto-end.
            return self.end(early=False)
        payload = {
            "session_id": self._session_id,
            "remaining_sec": remaining,
        }
        bus.publish("focus.tick", payload)
        return payload

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self, date_from: Optional[str] = None,
              date_to: Optional[str] = None) -> FocusStats:
        """Aggregate focus stats for a date range."""
        try:
            where = ["s.metadata_json LIKE '%\"kind\": \"focus\"%'"]
            args: List[Any] = []
            if date_from:
                where.append("s.started_at >= ?")
                args.append(date_from)
            if date_to:
                where.append("s.started_at <= ?")
                args.append(date_to)
            sql = (
                "SELECT COUNT(*) AS total_sessions, "
                "COALESCE(SUM(s.actual_min), 0) AS total_min, "
                "COALESCE(AVG(s.actual_min), 0) AS avg_min, "
                "SUM(CASE WHEN s.state='abandoned' THEN 1 ELSE 0 END) AS early, "
                "SUM(CASE WHEN s.state='completed' THEN 1 ELSE 0 END) AS complete "
                "FROM sessions s WHERE " + " AND ".join(where)
            )
            cur = db.get_conn().execute(sql, args)
            row = cur.fetchone()
            if not row:
                return FocusStats()
            # Count interruptions across all matching sessions.
            cur2 = db.get_conn().execute(
                "SELECT metadata_json FROM sessions s WHERE " +
                " AND ".join(where),
                args,
            )
            interruptions = 0
            for r in cur2.fetchall():
                try:
                    meta = json.loads(r["metadata_json"] or "{}")
                    interruptions += len(meta.get("interruptions", []) or [])
                except Exception:  # noqa: BLE001
                    pass
            return FocusStats(
                total_sessions=int(row["total_sessions"] or 0),
                total_focus_min=int(row["total_min"] or 0),
                avg_duration_min=round(float(row["avg_min"] or 0), 2),
                interruption_count=interruptions,
                early_end_count=int(row["early"] or 0),
                complete_count=int(row["complete"] or 0),
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return FocusStats()

    # ------------------------------------------------------------------
    # Restore-on-restart
    # ------------------------------------------------------------------

    def _restore_session_if_any(self) -> None:
        """If the app crashed mid-session, restore the session state."""
        try:
            sid = db.kv_get_int(ACTIVE_KEY, 0)
            if sid <= 0:
                return
            session = db.session_get(sid)
            if not session:
                db.kv_set(ACTIVE_KEY, "")
                return
            if session.get("state") not in ("running", "paused"):
                db.kv_set(ACTIVE_KEY, "")
                return
            self._session_id = sid
            self._title = (session.get("metadata") or {}).get("title", DEFAULT_TITLE)
            # Recompute ends_at from started_at + planned_min.
            try:
                start_dt = datetime.fromisoformat(
                    (session.get("started_at") or "").replace("Z", "+00:00"))
                planned = int(session.get("planned_min") or 0)
                self._ends_at = (start_dt + timedelta(minutes=planned)).isoformat()
            except Exception:  # noqa: BLE001
                self._ends_at = None
            meta = session.get("metadata") or {}
            self._interruption_count = len(meta.get("interruptions", []) or [])
            _log.info("Restored focus session %d (%d interruptions)",
                      sid, self._interruption_count)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

focus_mode: FocusMode = FocusMode()


# =============================================================================
# === UI Widget (lazy)                                                       ===
# =============================================================================

def _import_ctk():
    try:
        import customtkinter as ctk  # type: ignore
        return ctk
    except Exception:  # noqa: BLE001
        return None


class FocusModeWidget:
    """Minimal CustomTkinter widget showing time + interruption count."""

    def __init__(self, master: Any = None, *, lang: str = "fa") -> None:
        self.master = master
        self.lang = lang
        self._frame: Any = None
        self._after_id: Optional[str] = None
        self._last_tick_at: float = 0.0

    def build(self) -> Any:
        ctk = _import_ctk()
        if ctk is None:
            raise RuntimeError("CustomTkinter is not available")
        from .. import config

        f = ctk.CTkFrame(self.master, corner_radius=config.RADIUS_LG,
                          fg_color=config.CHARCOAL)
        self._frame = f

        # Title
        self._title = ctk.CTkLabel(
            f, text=i18n.t("focusMode", self.lang) or "حالت تمرکز",
            font=ctk.CTkFont(size=config.FONT_SIZE_HEADING_SM,
                              weight=config.FONT_WEIGHT_BOLD),
            text_color=config.GOLD,
        )
        self._title.pack(pady=(config.SPACE_LG, config.SPACE_XS))

        # Big countdown
        self._countdown = ctk.CTkLabel(
            f, text="50:00",
            font=ctk.CTkFont(size=config.FONT_SIZE_HERO,
                              weight=config.FONT_WEIGHT_BLACK),
            text_color=config.TEXT,
        )
        self._countdown.pack(pady=(config.SPACE_XS, config.SPACE_MD))

        # Interruptions + buttons row
        info_row = ctk.CTkFrame(f, fg_color="transparent")
        info_row.pack(pady=(0, config.SPACE_MD))
        self._interruptions_label = ctk.CTkLabel(
            info_row, text="⛔ 0",
            text_color=config.TEXT_DIM,
            font=ctk.CTkFont(size=config.FONT_SIZE_BODY_LG),
        )
        self._interruptions_label.pack(side="left", padx=10)

        self._interrupt_btn = ctk.CTkButton(
            info_row, text=i18n.t("addInterruption", self.lang) or "وقفه",
            width=80, command=self._on_interrupt,
            fg_color=config.SURFACE_HI, hover_color=config.SURFACE_HIGHER,
            text_color=config.TEXT,
        )
        self._interrupt_btn.pack(side="left", padx=6)

        # Start/End button
        self._toggle_btn = ctk.CTkButton(
            f, text=i18n.t("startFocus", self.lang) or "شروع تمرکز",
            height=42, command=self._on_toggle,
            fg_color=config.GOLD, hover_color=config.GOLD_SOFT,
            text_color=config.MATTE_BLACK,
            font=ctk.CTkFont(size=config.FONT_SIZE_DEFAULT,
                              weight=config.FONT_WEIGHT_BOLD),
        )
        self._toggle_btn.pack(pady=(0, config.SPACE_LG), padx=20, fill="x")

        self._refresh()
        self._schedule_tick()
        return f

    def _schedule_tick(self) -> None:
        if self._frame is None:
            return
        try:
            self._after_id = self._frame.after(500, self._on_tick)
        except Exception:  # noqa: BLE001
            pass

    def _on_tick(self) -> None:
        try:
            now = time.time()
            if now - self._last_tick_at >= 1.0:
                focus_mode.tick()
                self._last_tick_at = now
            self._refresh()
        finally:
            self._schedule_tick()

    def _refresh(self) -> None:
        if self._frame is None:
            return
        if focus_mode.is_active():
            sec = focus_mode.remaining_sec()
            m = sec // 60
            s = sec % 60
            text = f"{m:02d}:{s:02d}"
            if self.lang == "fa":
                text = i18n.to_fa_digits(text)
            self._countdown.configure(text=text)
            self._interruptions_label.configure(
                text=f"⛔ {i18n.to_fa_digits(focus_mode.interruption_count())}"
                if self.lang == "fa"
                else f"⛔ {focus_mode.interruption_count()}",
            )
            self._toggle_btn.configure(
                text=i18n.t("endFocus", self.lang) or "پایان تمرکز")
        else:
            self._countdown.configure(
                text=i18n.to_fa_digits("50:00") if self.lang == "fa" else "50:00")
            self._interruptions_label.configure(text="⛔ 0")
            self._toggle_btn.configure(
                text=i18n.t("startFocus", self.lang) or "شروع تمرکز")

    def _on_toggle(self) -> None:
        if focus_mode.is_active():
            focus_mode.end(early=True)
        else:
            focus_mode.start()
        self._refresh()

    def _on_interrupt(self) -> None:
        if focus_mode.is_active():
            focus_mode.add_interruption()
        self._refresh()

    def destroy(self) -> None:
        if self._after_id is not None:
            try:
                self._frame.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None
        if self._frame is not None:
            try:
                self._frame.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._frame = None


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== focus_mode self-tests ===")
    try:
        # Start with 1 min, end early.
        focus_mode.start(duration_min=1, title="Test focus",
                          block_internet=False, block_apps=[])
        assert focus_mode.is_active()
        assert focus_mode.interruption_count() == 0
        focus_mode.add_interruption("phone buzz")
        assert focus_mode.interruption_count() == 1
        result = focus_mode.end(early=True)
        assert not focus_mode.is_active()
        assert result.get("interruption_count") == 1
        print("  OK   lifecycle")
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
