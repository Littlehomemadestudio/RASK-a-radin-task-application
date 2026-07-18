"""
rask.services
=============

Service layer for the Rask desktop application.

Each module in this package exposes a module-level singleton instance
of its service class.  Services wrap the raw :mod:`rask.database`
repository functions with business logic, input validation,
invariant enforcement, and event-bus publication.

The singletons are imported lazily so that the entire package can be
imported without paying the cost of importing optional dependencies
(``reportlab``, ``speech_recognition``, etc.) until the corresponding
service is actually used.

Typical usage::

    from rask.services import activity_service, goal_service

    act = activity_service.add(title="Reading", category_id=1, duration_min=30)

To initialize every service at startup (e.g. resume persisted timers,
load settings cache), call :func:`init_all` once after
:func:`rask.database.open_db`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "activity_service",
    "goal_service",
    "streak_service",
    "stats_service",
    "backup_service",
    "export_service",
    "voice_service",
    "reminder_service",
    "template_service",
    "badge_service",
    "recurring_service",
    "timer_service",
    "settings_service",
    "init_all",
]

# -----------------------------------------------------------------------------
# Lazy singleton accessors
# -----------------------------------------------------------------------------
# We import the service instances eagerly here — the modules themselves
# only import heavy optional dependencies (reportlab, speech_recognition,
# pyaudio) inside method bodies or guarded try/except blocks, so importing
# the package is cheap and side-effect-free.

from .activity_service import activity_service, ActivityService  # noqa: E402
from .streak_service import streak_service, StreakService  # noqa: E402
from .badge_service import badge_service, BadgeService  # noqa: E402
from .goal_service import goal_service, GoalService  # noqa: E402
from .template_service import template_service, TemplateService  # noqa: E402
from .reminder_service import reminder_service, ReminderService  # noqa: E402
from .recurring_service import recurring_service, RecurringService  # noqa: E402
from .timer_service import timer_service, TimerService  # noqa: E402
from .settings_service import settings_service, SettingsService  # noqa: E402
from .backup_service import backup_service, BackupService  # noqa: E402
from .voice_service import voice_service, VoiceService  # noqa: E402
from .export_service import export_service, ExportService  # noqa: E402
from .stats_service import stats_service, StatsService  # noqa: E402


def init_all() -> None:
    """Initialize every service in dependency order.

    Call this once after :func:`rask.database.open_db` at application
    startup.  Each service's ``init()`` method performs idempotent
    setup tasks such as:
      - loading cached settings into memory
      - resuming a persisted background timer
      - resetting the reminder scheduler's last-fired markers
      - re-running badge checks against current state

    Services that have no init-time work simply define a no-op
    ``init()`` method.  This function never raises — exceptions are
    logged via :mod:`rask.core.logging_utils` and swallowed so a single
    broken service cannot prevent the app from starting.
    """
    from ..core.logging_utils import get_logger, log_exception
    log = get_logger("services.init")

    order = (
        settings_service,
        activity_service,
        streak_service,
        badge_service,
        goal_service,
        template_service,
        reminder_service,
        recurring_service,
        timer_service,
        backup_service,
        voice_service,
        export_service,
        stats_service,
    )
    for svc in order:
        try:
            init = getattr(svc, "init", None)
            if callable(init):
                init()
        except Exception as exc:  # noqa: BLE001
            log_exception(log, exc, {"service": type(svc).__name__})
            log.warning("Service %s.init() failed: %s",
                        type(svc).__name__, exc)
