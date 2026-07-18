"""
rask.features
=============

Extended feature modules for the Rask desktop application.

This package groups together high-level "vertical slice" features that
build on top of the core services layer (``rask.services.*``) and the
persistence layer (``rask.database``).  Each module exposes a
module-level singleton service instance plus, where appropriate, a
CustomTkinter widget and/or dialog for in-app integration.

Feature modules
---------------

``pomodoro``               — Pomodoro timer service + widget + dialog
``time_blocking``          — Time blocking with conflict detection
``journal``                — Daily journal entries (mood/energy/gratitudes)
``habits``                 — Habit tracker with streaks and completion rate
``mood_tracker``           — Standalone mood/energy tracking
``focus_mode``             — Deep-focus mode with distraction blocking
``smart_insights``         — AI-like insight engine
``notifications_center``   — In-app notification center
``achievements_system``    — Extended achievement/XP/level system
``weekly_review``          — Weekly review generator (text/HTML/Markdown)
``import_export_extra``    — CSV/JSON/WebPWA/iCal/Markdown/HTML
``calendar_integration``   — Calendar views (month/week/day) + free-time
``quick_actions``          — Quick action shortcuts and panel
``sound_effects``          — Cross-platform sound effects
``themes_extra``           — Extra theme palettes (8 themes)
``backup_scheduler``       — Periodic backup scheduler
``analytics_dashboard``    — Advanced analytics (heatmap, forecast, etc.)

Design conventions
-------------------

1. **Module-level singletons.**  Every service is instantiated once at
   module load time as ``<name>_service`` (e.g. ``pomodoro_service``).
   Importing the module is cheap and safe from any thread.

2. **Persistence via ``rask.database``.**  Each module owns one or more
   SQLite tables.  The schema SQL is applied lazily on first use
   (idempotent ``CREATE TABLE IF NOT EXISTS``) so the rest of the app
   does not need to know about feature-specific tables.

3. **Event-bus publication.**  Every state-changing method publishes an
   event on ``rask.core.event_bus.bus``.  Event names follow the
   ``<feature>.<action>`` convention (e.g. ``pomodoro.phase_changed``).

4. **Persian-first i18n.**  All user-visible strings flow through
   ``rask.i18n.t`` / ``tr`` and digits are localized via
   ``i18n.to_fa_digits`` when ``lang="fa"``.

5. **Python 3.9 compatible.**  All type hints use ``from __future__
   import annotations`` so modern syntax (``list[X]``, ``X | None``)
   works on 3.9.

6. **Lazy CustomTkinter imports.**  Service classes never import
   CustomTkinter at module load time; widget classes do, but the
   service singleton can be constructed headless (useful for tests and
   CLI).
"""
from __future__ import annotations

__version__: str = "1.0.0"

__all__: list[str] = [
    "pomodoro",
    "time_blocking",
    "journal",
    "habits",
    "mood_tracker",
    "focus_mode",
    "smart_insights",
    "notifications_center",
    "achievements_system",
    "weekly_review",
    "import_export_extra",
    "calendar_integration",
    "quick_actions",
    "sound_effects",
    "themes_extra",
    "backup_scheduler",
    "analytics_dashboard",
]


# =============================================================================
# === Lazy accessors                                                          ===
# =============================================================================
# We intentionally do NOT import the submodules at package import time.
# Each submodule pulls in the database, services layer, and possibly
# CustomTkinter — loading all 17 eagerly at startup would add ~200 ms
# of import overhead for no benefit.  Instead, callers import the
# specific module they need:
#
#     from rask.features import pomodoro
#     pomodoro.pomodoro_service.start()
#
# For introspection / debugging we expose a helper that lists every
# feature module that can be imported.

def available_features() -> list[str]:
    """Return a sorted list of feature module names that can be imported.

    This does NOT actually import the modules — it just checks that
    the corresponding ``.py`` file exists in this directory.  Useful
    for the About screen and the CLI's ``features list`` command.
    """
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    out: list[str] = []
    for name in __all__:
        path = os.path.join(here, f"{name}.py")
        if os.path.exists(path):
            out.append(name)
    return sorted(out)


def feature_description(name: str) -> str:
    """Return a short Persian/English description of a feature module.

    Falls back to the empty string if `name` is unknown.
    """
    return _FEATURE_DESCRIPTIONS.get(name, "")


_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "pomodoro": "تایمر پومودورو با چرخه‌های کار/استراحت",
    "time_blocking": "بلوک‌بندی زمانی با تشخیص تداخل",
    "journal": "دفترچه روزانه با حال و انرژی",
    "habits": "ردیاب عادت با زنجیره و نرخ تکمیل",
    "mood_tracker": "ردیاب مستقل حال و انرژی",
    "focus_mode": "حالت تمرکز عمیق با مسدودسازی حواس‌پرتی",
    "smart_insights": "موتور بینش هوشمند",
    "notifications_center": "مرکز اعلان‌های درون‌برنامه‌ای",
    "achievements_system": "سیستم گسترده دستاورد و XP",
    "weekly_review": "تولیدکننده مرور هفتگی",
    "import_export_extra": "قالب‌های اضافی واردات/خروجی",
    "calendar_integration": "نمای تقویمی ماه/هفته/روز",
    "quick_actions": "پنل عملیات سریع",
    "sound_effects": "افکت‌های صوتی چندسکویی",
    "themes_extra": "پوسته‌های اضافی (۸ تم)",
    "backup_scheduler": "زمان‌بند پشتیبان خودکار",
    "analytics_dashboard": "تحلیل‌های پیشرفته و پیش‌بینی",
}
