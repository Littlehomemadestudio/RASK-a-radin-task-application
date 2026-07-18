"""
rask.ui.screens
===============

Top-level screen (view) classes for the Rask desktop application.

A *screen* is a full-viewport :class:`customtkinter.CTkFrame` that
fills the area above the bottom navigation bar.  The :class:`App`
shell switches between screens by hiding one and showing another,
calling ``refresh()`` on the newly-shown screen so it always reflects
the latest data.

Every screen follows the same construction contract::

    Screen(parent, app, lang="fa")

where ``app`` is the main application object (exposing
``open_quick_log``, ``open_goal_dialog``, ``switch_tab``,
``show_toast``, ``show_lock``, etc.).  Screens subscribe to
``event_bus.bus`` events in their ``__init__`` and unsubscribe in
``destroy()`` so they never leak references.

Conventions
-----------
* Every screen subclasses :class:`ctk.CTkFrame`.
* Every screen exposes a ``refresh()`` method to re-render data.
* All Persian digits flow through :func:`i18n.to_fa_digits`.
* All translatable strings flow through :func:`i18n.t` / :func:`i18n.tr`.
* All colors come from :mod:`rask.config` (gold-on-dark theme).
* RTL layout is applied automatically when ``lang="fa"``.

Public screens
--------------
``SplashView``         — animated splash screen (logo pulse + gold dust)
``OnboardingView``     — 3-slide welcome flow
``LockView``           — full-screen PIN pad with shake-on-wrong animation
``HomeScreen``         — greeting + today ring + templates + recent activities
``GoalsScreen``        — daily/weekly/monthly goals with progress rings + streaks
``StatsScreen``        — charts (bar/line/donut/heatmap) + insights
``InsightsScreen``     — personality card + best-time charts + recommendations
``SettingsScreen``     — collapsible sections of every user preference
``TemplatesScreen``    — quick-log templates browser
``RemindersScreen``    — time-based reminders browser
``BadgesScreen``       — gamification badges grid + confetti
``ProfileScreen``      — user identity + stats + achievements preview
``CategoriesScreen``   — activity categories browser
``SearchScreen``       — full-screen search overlay
``BackupScreen``       — encrypted backup / restore UI
``AboutScreen``        — about-the-app metadata + changelog
``ShortcutsScreen``    — keyboard shortcuts help modal
"""
from __future__ import annotations

__all__ = [
    "SplashView",
    "OnboardingView",
    "LockView",
    "HomeScreen",
    "GoalsScreen",
    "StatsScreen",
    "InsightsScreen",
    "SettingsScreen",
    "TemplatesScreen",
    "RemindersScreen",
    "BadgesScreen",
    "ProfileScreen",
    "CategoriesScreen",
    "SearchScreen",
    "BackupScreen",
    "AboutScreen",
    "ShortcutsScreen",
    # Feature screens (Task 11)
    "PomodoroScreen",
    "JournalScreen",
    "HabitsScreen",
    "MoodScreen",
    "FocusScreen",
    "InsightsDetailScreen",
    "NotificationsScreen",
    "AchievementsScreen",
    "WeeklyReviewScreen",
    "CalendarScreen",
    "QuickActionsScreen",
    "AnalyticsScreen",
    "SCREENS",
    "FEATURE_SCREENS",
]

from .splash_screen import SplashView
from .onboarding_screen import OnboardingView
from .lock_screen import LockView
from .home_screen import HomeScreen
from .goals_screen import GoalsScreen
from .stats_screen import StatsScreen
from .insights_screen import InsightsScreen
from .settings_screen import SettingsScreen
from .templates_screen import TemplatesScreen
from .reminders_screen import RemindersScreen
from .badges_screen import BadgesScreen
from .profile_screen import ProfileScreen
from .categories_screen import CategoriesScreen
from .search_screen import SearchScreen
from .backup_screen import BackupScreen
from .about_screen import AboutScreen
from .shortcuts_screen import ShortcutsScreen

# Feature screens (Task 11) — built on top of the rask.features.* layer.
from .pomodoro_screen import PomodoroScreen
from .journal_screen import JournalScreen
from .habits_screen import HabitsScreen
from .mood_screen import MoodScreen
from .focus_screen import FocusScreen
from .insights_detail_screen import InsightsDetailScreen
from .notifications_screen import NotificationsScreen
from .achievements_screen import AchievementsScreen
from .weekly_review_screen import WeeklyReviewScreen
from .calendar_screen import CalendarScreen
from .quick_actions_screen import QuickActionsScreen
from .analytics_screen import AnalyticsScreen


# Registry mapping the bottom-nav tab keys to screen classes.
# Used by :class:`rask.app.App` to instantiate the right screen on
# tab-switch.  ``splash``, ``onboarding``, ``lock``, ``search``,
# ``backup``, ``about``, and ``shortcuts`` are special-case
# full-screen overlays that are not part of the bottom nav but are
# listed here for completeness.
SCREENS: dict[str, type] = {
    "splash": SplashView,
    "onboarding": OnboardingView,
    "lock": LockView,
    "home": HomeScreen,
    "goals": GoalsScreen,
    "stats": StatsScreen,
    "insights": InsightsScreen,
    "settings": SettingsScreen,
    "templates": TemplatesScreen,
    "reminders": RemindersScreen,
    "badges": BadgesScreen,
    "profile": ProfileScreen,
    "categories": CategoriesScreen,
    "search": SearchScreen,
    "backup": BackupScreen,
    "about": AboutScreen,
    "shortcuts": ShortcutsScreen,
}

#: Feature screens built on top of the rask.features.* layer (Task 11).
#: These are not part of the bottom-nav by default; the app can wire
#: them to the nav or open them as overlays / quick-action targets.
FEATURE_SCREENS: dict[str, type] = {
    "pomodoro": PomodoroScreen,
    "journal": JournalScreen,
    "habits": HabitsScreen,
    "mood": MoodScreen,
    "focus": FocusScreen,
    "insights_detail": InsightsDetailScreen,
    "notifications": NotificationsScreen,
    "achievements": AchievementsScreen,
    "weekly_review": WeeklyReviewScreen,
    "calendar": CalendarScreen,
    "quick_actions": QuickActionsScreen,
    "analytics": AnalyticsScreen,
}
