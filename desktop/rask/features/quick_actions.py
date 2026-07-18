"""
rask.features.quick_actions
===========================

Quick action shortcuts — a single-tap way to trigger common operations.

Each action has:

  • ``id``            — stable identifier
  • ``name``          — Persian display name
  • ``icon``          — emoji or icon key
  • ``shortcut``      — keyboard shortcut (e.g. "Ctrl+Shift+F")
  • ``action_type``   — one of: ``start_focus``, ``log_activity``,
                        ``start_timer``, ``quick_log``,
                        ``open_weekly_review``, ``export_today``,
                        ``backup_now``, ``lock_app``, ``open_screen``
  • ``action_payload``— dict of parameters for the action

Pre-registered actions cover the most common use cases (start a 25-min
focus, log 30-min reading, log 1-hour workout, start timer with last
category, quick-log last activity, open weekly review, export today's
report, backup now, lock app).

The :class:`QuickActionsPanel` UI widget renders a 3-column grid of
buttons, each triggering :meth:`QuickActionsService.execute`.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import today_iso

__all__ = [
    "QuickAction",
    "QuickActionsService",
    "quick_actions_service",
    "QuickActionsPanel",
    "ACTION_START_FOCUS",
    "ACTION_LOG_ACTIVITY",
    "ACTION_START_TIMER",
    "ACTION_QUICK_LOG",
    "ACTION_OPEN_WEEKLY_REVIEW",
    "ACTION_EXPORT_TODAY",
    "ACTION_BACKUP_NOW",
    "ACTION_LOCK_APP",
    "ACTION_OPEN_SCREEN",
]

_log = get_logger("features.quick_actions")


# =============================================================================
# === Action types                                                           ===
# =============================================================================

ACTION_START_FOCUS: str = "start_focus"
ACTION_LOG_ACTIVITY: str = "log_activity"
ACTION_START_TIMER: str = "start_timer"
ACTION_QUICK_LOG: str = "quick_log"
ACTION_OPEN_WEEKLY_REVIEW: str = "open_weekly_review"
ACTION_EXPORT_TODAY: str = "export_today"
ACTION_BACKUP_NOW: str = "backup_now"
ACTION_LOCK_APP: str = "lock_app"
ACTION_OPEN_SCREEN: str = "open_screen"


# =============================================================================
# === Data class                                                             ===
# =============================================================================

@dataclass
class QuickAction:
    """A single quick action."""

    id: str
    name: str
    icon: str
    shortcut: Optional[str] = None
    action_type: str = ACTION_QUICK_LOG
    action_payload: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    order_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# === Pre-registered actions                                                 ===
# =============================================================================

DEFAULT_ACTIONS: List[QuickAction] = [
    QuickAction(
        id="focus_25",
        name="۲۵ دقیقه تمرکز",
        icon="🎯",
        shortcut="Ctrl+Shift+F",
        action_type=ACTION_START_FOCUS,
        action_payload={"duration_min": 25, "title": "تمرکز"},
        order_index=10,
    ),
    QuickAction(
        id="reading_30",
        name="۳۰ دقیقه مطالعه",
        icon="📚",
        shortcut="Ctrl+Shift+R",
        action_type=ACTION_LOG_ACTIVITY,
        action_payload={"title": "مطالعه", "category_key": "LEARN",
                         "duration_min": 30},
        order_index=20,
    ),
    QuickAction(
        id="workout_60",
        name="۱ ساعت ورزش",
        icon="💪",
        shortcut="Ctrl+Shift+W",
        action_type=ACTION_LOG_ACTIVITY,
        action_payload={"title": "ورزش", "category_key": "HEALTH",
                         "duration_min": 60},
        order_index=30,
    ),
    QuickAction(
        id="timer_last_cat",
        name="تایمر با آخرین دسته",
        icon="⏱",
        shortcut="Ctrl+Shift+T",
        action_type=ACTION_START_TIMER,
        action_payload={},
        order_index=40,
    ),
    QuickAction(
        id="quick_log_last",
        name="ثبت سریع آخرین فعالیت",
        icon="⚡",
        shortcut="Ctrl+Shift+L",
        action_type=ACTION_QUICK_LOG,
        action_payload={},
        order_index=50,
    ),
    QuickAction(
        id="weekly_review",
        name="مرور هفتگی",
        icon="📋",
        shortcut="Ctrl+Shift+V",
        action_type=ACTION_OPEN_WEEKLY_REVIEW,
        action_payload={},
        order_index=60,
    ),
    QuickAction(
        id="export_today",
        name="خروجی امروز",
        icon="📤",
        shortcut="Ctrl+Shift+E",
        action_type=ACTION_EXPORT_TODAY,
        action_payload={"format": "pdf"},
        order_index=70,
    ),
    QuickAction(
        id="backup_now",
        name="پشتیبان‌گیری",
        icon="💾",
        shortcut="Ctrl+Shift+B",
        action_type=ACTION_BACKUP_NOW,
        action_payload={},
        order_index=80,
    ),
    QuickAction(
        id="lock_app",
        name="قفل برنامه",
        icon="🔒",
        shortcut="Ctrl+Shift+K",
        action_type=ACTION_LOCK_APP,
        action_payload={},
        order_index=90,
    ),
]


# =============================================================================
# === QuickActionsService                                                    ===
# =============================================================================

class QuickActionsService:
    """Quick action registry + execution."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._actions: Dict[str, QuickAction] = {}
        self._shortcuts: Dict[str, str] = {}  # shortcut -> action_id
        self._action_handlers: Dict[str, Callable[[Dict[str, Any]], bool]] = {}
        self._register_defaults()
        self._register_default_handlers()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, action: QuickAction) -> None:
        """Register a quick action.  Overwrites if id already exists."""
        with self._lock:
            self._actions[action.id] = action
            if action.shortcut:
                self._shortcuts[action.shortcut.lower()] = action.id
            bus.publish("quick_action.registered", action.to_dict())

    def unregister(self, action_id: str) -> bool:
        with self._lock:
            action = self._actions.pop(action_id, None)
            if action is None:
                return False
            if action.shortcut:
                self._shortcuts.pop(action.shortcut.lower(), None)
            return True

    def register_handler(self, action_type: str,
                          handler: Callable[[Dict[str, Any]], bool]) -> None:
        """Register a handler for an action_type.

        The handler is called with the action_payload and returns True
        on success.  Only one handler per action_type is supported;
        re-registering overwrites the previous handler.
        """
        with self._lock:
            self._action_handlers[action_type] = handler

    def _register_defaults(self) -> None:
        for action in DEFAULT_ACTIONS:
            self._actions[action.id] = action
            if action.shortcut:
                self._shortcuts[action.shortcut.lower()] = action.id

    def _register_default_handlers(self) -> None:
        """Register the built-in handlers."""
        self._action_handlers[ACTION_START_FOCUS] = self._handle_start_focus
        self._action_handlers[ACTION_LOG_ACTIVITY] = self._handle_log_activity
        self._action_handlers[ACTION_START_TIMER] = self._handle_start_timer
        self._action_handlers[ACTION_QUICK_LOG] = self._handle_quick_log
        self._action_handlers[ACTION_OPEN_WEEKLY_REVIEW] = self._handle_open_weekly_review
        self._action_handlers[ACTION_EXPORT_TODAY] = self._handle_export_today
        self._action_handlers[ACTION_BACKUP_NOW] = self._handle_backup_now
        self._action_handlers[ACTION_LOCK_APP] = self._handle_lock_app
        self._action_handlers[ACTION_OPEN_SCREEN] = self._handle_open_screen

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list(self) -> List[QuickAction]:
        """Return all registered actions, sorted by order_index."""
        with self._lock:
            return sorted([a for a in self._actions.values() if a.enabled],
                           key=lambda a: a.order_index)

    def by_id(self, action_id: str) -> Optional[QuickAction]:
        with self._lock:
            return self._actions.get(action_id)

    def by_shortcut(self, shortcut: str) -> Optional[QuickAction]:
        """Look up an action by its keyboard shortcut (case-insensitive)."""
        if not shortcut:
            return None
        with self._lock:
            action_id = self._shortcuts.get(shortcut.lower())
            if action_id is None:
                return None
            return self._actions.get(action_id)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, action_id: str) -> bool:
        """Execute the action by id.  Returns True on success."""
        action = self.by_id(action_id)
        if action is None:
            _log.warning("Unknown quick action: %s", action_id)
            return False
        return self._execute_action(action)

    def execute_shortcut(self, shortcut: str) -> bool:
        """Execute the action bound to `shortcut`.  Returns True on success."""
        action = self.by_shortcut(shortcut)
        if action is None:
            return False
        return self._execute_action(action)

    def _execute_action(self, action: QuickAction) -> bool:
        handler = self._action_handlers.get(action.action_type)
        if handler is None:
            _log.warning("No handler for action_type=%r", action.action_type)
            return False
        try:
            ok = bool(handler(action.action_payload))
            bus.publish("quick_action.executed", {
                "id": action.id,
                "action_type": action.action_type,
                "success": ok,
            })
            if ok:
                _log.info("Quick action executed: %s", action.id)
            return ok
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": action.id})
            bus.publish("quick_action.executed", {
                "id": action.id,
                "action_type": action.action_type,
                "success": False,
                "error": str(exc),
            })
            return False

    # ------------------------------------------------------------------
    # Built-in handlers
    # ------------------------------------------------------------------

    def _handle_start_focus(self, payload: Dict[str, Any]) -> bool:
        from .focus_mode import focus_mode
        duration = int(payload.get("duration_min", 25))
        title = payload.get("title", "Deep Focus")
        focus_mode.start(duration_min=duration, title=title)
        return True

    def _handle_log_activity(self, payload: Dict[str, Any]) -> bool:
        try:
            from ..services.activity_service import activity_service
            cat_id = None
            cat_key = payload.get("category_key")
            if cat_key:
                cat = db.category_get_by_key(cat_key)
                if cat:
                    cat_id = int(cat["id"])
            else:
                cat_name = payload.get("category_name")
                if cat_name:
                    for c in db.category_list():
                        if (c.get("name_en", "").lower() == cat_name.lower()
                                or c.get("name_fa", "") == cat_name):
                            cat_id = int(c["id"])
                            break
            activity_service.add(
                title=payload.get("title", "Activity"),
                category_id=cat_id,
                duration_min=int(payload.get("duration_min", 30)),
                date_iso=today_iso(),
                kind="manual",
                source="desktop",
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return False

    def _handle_start_timer(self, payload: Dict[str, Any]) -> bool:
        """Start a stopwatch with the user's last-used category."""
        try:
            from ..services.activity_service import activity_service
            recent = activity_service.recent(limit=1)
            title = "ضبط زمان"
            cat_id = None
            if recent:
                cat_id = recent[0].get("category_id")
                title = recent[0].get("title", title)
            activity_service.start_recording(title=title, category_id=cat_id)
            return True
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return False

    def _handle_quick_log(self, payload: Dict[str, Any]) -> bool:
        """Open the quick-log dialog (publishes an event the UI listens to)."""
        bus.publish("ui.quick_log_requested", {})
        return True

    def _handle_open_weekly_review(self, payload: Dict[str, Any]) -> bool:
        """Open the weekly review screen/dialog."""
        bus.publish("ui.weekly_review_requested", {})
        return True

    def _handle_export_today(self, payload: Dict[str, Any]) -> bool:
        """Trigger an export of today's data."""
        fmt = payload.get("format", "pdf")
        bus.publish("ui.export_requested", {
            "format": fmt,
            "date_from": today_iso(),
            "date_to": today_iso(),
        })
        return True

    def _handle_backup_now(self, payload: Dict[str, Any]) -> bool:
        """Trigger an immediate backup."""
        try:
            from ..services.backup_service import backup_service
            # Run in background; UI may show progress.
            backup_service.create_backup_background()  # type: ignore[attr-defined]
            return True
        except AttributeError:
            # Fallback: publish event for the UI to handle.
            bus.publish("ui.backup_requested", {})
            return True
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return False

    def _handle_lock_app(self, payload: Dict[str, Any]) -> bool:
        """Lock the app immediately."""
        bus.publish("ui.lock_requested", {})
        return True

    def _handle_open_screen(self, payload: Dict[str, Any]) -> bool:
        """Open a named screen."""
        screen = payload.get("screen")
        if not screen:
            return False
        bus.publish("ui.navigate", {"screen": screen})
        return True


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

quick_actions_service: QuickActionsService = QuickActionsService()


# =============================================================================
# === UI Panel (lazy CustomTkinter)                                          ===
# =============================================================================

def _import_ctk():
    try:
        import customtkinter as ctk  # type: ignore
        return ctk
    except Exception:  # noqa: BLE001
        return None


class QuickActionsPanel:
    """CustomTkinter panel showing a grid of quick action buttons."""

    def __init__(self, master: Any = None, *, lang: str = "fa",
                 columns: int = 3) -> None:
        self.master = master
        self.lang = lang
        self.columns = columns
        self._frame: Any = None
        self._buttons: List[Any] = []

    def build(self) -> Any:
        ctk = _import_ctk()
        if ctk is None:
            raise RuntimeError("CustomTkinter is not available")
        from .. import config

        f = ctk.CTkFrame(self.master, fg_color="transparent")
        self._frame = f

        # Title row
        title = ctk.CTkLabel(
            f, text=i18n.t("quickActions", self.lang) or "عملیات سریع",
            font=ctk.CTkFont(size=config.FONT_SIZE_HEADING_SM,
                              weight=config.FONT_WEIGHT_BOLD),
            text_color=config.GOLD,
        )
        title.pack(anchor="e", pady=(0, config.SPACE_MD))

        # Grid
        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(fill="x")
        actions = quick_actions_service.list()
        for i, action in enumerate(actions):
            row = i // self.columns
            col = i % self.columns
            btn = ctk.CTkButton(
                grid,
                text=f"{action.icon}  {action.name}",
                height=64,
                corner_radius=config.RADIUS_MD,
                fg_color=config.SURFACE_HI,
                hover_color=config.SURFACE_HIGHER,
                text_color=config.TEXT,
                font=ctk.CTkFont(size=config.FONT_SIZE_BODY),
                command=lambda aid=action.id: self._on_click(aid),
            )
            btn.grid(row=row, column=col, padx=4, pady=4,
                     sticky="nsew")
            self._buttons.append(btn)
        # Make columns equal-weight.
        for c in range(self.columns):
            grid.grid_columnconfigure(c, weight=1)
        return f

    def _on_click(self, action_id: str) -> None:
        quick_actions_service.execute(action_id)

    def destroy(self) -> None:
        if self._frame is not None:
            try:
                self._frame.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._frame = None
        self._buttons.clear()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== quick_actions self-tests ===")
    try:
        actions = quick_actions_service.list()
        assert len(actions) >= 9, f"expected >=9 actions, got {len(actions)}"
        # by_shortcut
        a = quick_actions_service.by_shortcut("Ctrl+Shift+F")
        assert a is not None and a.id == "focus_25"
        # Custom action
        quick_actions_service.register(QuickAction(
            id="test_custom",
            name="Test",
            icon="🔧",
            shortcut="Ctrl+Shift+0",
            action_type=ACTION_OPEN_SCREEN,
            action_payload={"screen": "test"},
        ))
        a = quick_actions_service.by_id("test_custom")
        assert a is not None
        quick_actions_service.unregister("test_custom")
        assert quick_actions_service.by_id("test_custom") is None
        print("  OK   registry + shortcut lookup")
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
