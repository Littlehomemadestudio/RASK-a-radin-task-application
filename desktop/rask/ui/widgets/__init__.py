"""
rask.ui.widgets
===============

Comprehensive widget library for the Rask desktop app.

Every widget is built on CustomTkinter and uses the gold-on-dark theme
from :mod:`rask.config`.  All widgets respect RTL layout when
``lang="fa"`` is passed.

Submodules
----------
theme            — ThemeManager singleton + font/color helpers
icons            — Procedural Pillow-drawn icon registry
buttons          — GoldButton, GhostButton, TextButton, IconButton, etc.
inputs           — GoldEntry, PasswordEntry, SearchEntry, PinEntry, etc.
toggles          — Toggle, RadioButton, CheckBox, SegmentedControl
sliders          — GoldSlider, RangeSlider, ProgressBar, StepProgress, RatingStars
cards            — Card, StatCard, ActivityCard, GoalCard, etc.
list_items       — ListItem + domain-specific variants
headers          — Header, TabHeader, SearchHeader
dividers         — Divider, Spacer, SectionTitle, Pill
badges           — Chip, CategoryBadge, TierBadge, StreakBadge, CountBadge
progress_ring    — Animated ProgressRing + MultiProgressRing
charts           — BarChart, LineChart, DonutChart, Heatmap, Sparkline, etc.
bottom_nav       — BottomNav with sliding indicator + FAB slot
live_timer       — LiveTimer display subscribing to timer_service events
animated_label   — AnimatedLabel, TypewriterLabel, CountUpLabel
avatars          — Circular Avatar with initials/image/ring
empty_state      — EmptyState placeholder (icon + title + subtitle + action)
skeleton         — Animated shimmer loading placeholders
tooltips         — Hover tooltip service (attach/detach)
dialogs          — BaseDialog, AlertDialog, ConfirmDialog, PromptDialog, etc.
sheets           — ActionSheet, PickerSheet, FilterSheet, SortSheet, ShareSheet
toasts           — Toast + ToastManager (info/success/warning/error/achievement)
confetti         — Confetti celebration overlay
calendar_grid    — Month-view CalendarGrid (Jalali + Gregorian)
date_picker      — DatePicker bottom sheet using CalendarGrid
time_picker      — TimePicker bottom sheet with steppers + presets
scrollable       — SmoothScrollFrame, VirtualList, ParallaxHeader
pull_to_refresh  — PullToRefresh wrapper for scrollable frames

Quick start
-----------
>>> import customtkinter as ctk
>>> from rask.ui.widgets import GoldButton, Card, ProgressRing, theme
>>> theme.apply()
>>> btn = GoldButton(text="ذخیره", lang="fa")
"""
from __future__ import annotations

# Theme manager (must come first — others depend on it)
# NOTE: we deliberately do NOT do `from .theme import theme` here, because
# that would overwrite the `theme` submodule attribute on the package and
# break the `from . import theme as _theme` import idiom used by every
# other widget module.  Consumers wanting the singleton should use
# `from rask.ui.widgets.theme import theme` directly.
from .theme import ThemeManager, get_font
from .theme import theme as default_theme

# Icon registry
from .icons import icon, icon_glyph, has_icon, ICON_NAMES

# Buttons
from .buttons import (
    GoldButton, GhostButton, TextButton, IconButton,
    DangerButton, SuccessButton, PillButton, FabButton,
    SegmentedButton,
)

# Inputs
from .inputs import (
    GoldEntry, PasswordEntry, SearchEntry, TextArea,
    NumberEntry, TimeEntry, DurationEntry, PinEntry,
)

# Toggles
from .toggles import Toggle, RadioButton, CheckBox, SegmentedControl

# Sliders & progress
from .sliders import (
    GoldSlider, RangeSlider, ProgressBar, StepProgress, RatingStars,
)

# Cards
from .cards import (
    Card, StatCard, ActivityCard, GoalCard, TemplateCard,
    BadgeCard, ReminderCard, SettingCard, SummaryCard,
)

# List items
from .list_items import (
    ListItem, ActivityListItem, GoalListItem,
    TemplateListItem, ReminderListItem, BadgeListItem,
    CategoryListItem,
)

# Headers
from .headers import Header, TabHeader, SearchHeader

# Dividers
from .dividers import Divider, Spacer, SectionTitle, Pill

# Badges
from .badges import (
    Chip, CategoryBadge, TagChip, TierBadge, StreakBadge, CountBadge,
)

# Progress rings
from .progress_ring import ProgressRing, MultiProgressRing

# Charts
from .charts import (
    BarChart, LineChart, DonutChart, Heatmap,
    Sparkline, RadarChart, Histogram,
)

# Bottom nav
from .bottom_nav import BottomNav

# Live timer
from .live_timer import LiveTimer

# Animated labels
from .animated_label import AnimatedLabel, TypewriterLabel, CountUpLabel

# Avatars
from .avatars import Avatar, AVATAR_COLORS

# Empty state
from .empty_state import EmptyState

# Skeleton loading
from .skeleton import Skeleton, SkeletonCard, SkeletonList

# Tooltips
from .tooltips import Tooltip

# Dialogs
from .dialogs import (
    BaseDialog, AlertDialog, ConfirmDialog,
    PromptDialog, ChoiceDialog, BottomSheet,
)

# Sheets
from .sheets import (
    ActionSheet, PickerSheet, FilterSheet,
    SortSheet, ShareSheet,
)

# Toasts
from .toasts import Toast, ToastManager

# Confetti
from .confetti import Confetti

# Calendar grid
from .calendar_grid import CalendarGrid

# Date picker
from .date_picker import DatePicker

# Time picker
from .time_picker import TimePicker

# Scrollable containers
from .scrollable import SmoothScrollFrame, VirtualList, ParallaxHeader

# Pull-to-refresh
from .pull_to_refresh import PullToRefresh


__all__ = [
    # Theme
    "ThemeManager", "get_font", "default_theme",
    # Note: ``theme`` is the submodule, accessible via
    # ``from rask.ui.widgets.theme import theme`` for the singleton.
    # Icons
    "icon", "icon_glyph", "has_icon", "ICON_NAMES",
    # Buttons
    "GoldButton", "GhostButton", "TextButton", "IconButton",
    "DangerButton", "SuccessButton", "PillButton", "FabButton",
    "SegmentedButton",
    # Inputs
    "GoldEntry", "PasswordEntry", "SearchEntry", "TextArea",
    "NumberEntry", "TimeEntry", "DurationEntry", "PinEntry",
    # Toggles
    "Toggle", "RadioButton", "CheckBox", "SegmentedControl",
    # Sliders & progress
    "GoldSlider", "RangeSlider", "ProgressBar", "StepProgress",
    "RatingStars",
    # Cards
    "Card", "StatCard", "ActivityCard", "GoalCard", "TemplateCard",
    "BadgeCard", "ReminderCard", "SettingCard", "SummaryCard",
    # List items
    "ListItem", "ActivityListItem", "GoalListItem",
    "TemplateListItem", "ReminderListItem", "BadgeListItem",
    "CategoryListItem",
    # Headers
    "Header", "TabHeader", "SearchHeader",
    # Dividers
    "Divider", "Spacer", "SectionTitle", "Pill",
    # Badges
    "Chip", "CategoryBadge", "TagChip", "TierBadge",
    "StreakBadge", "CountBadge",
    # Progress rings
    "ProgressRing", "MultiProgressRing",
    # Charts
    "BarChart", "LineChart", "DonutChart", "Heatmap",
    "Sparkline", "RadarChart", "Histogram",
    # Bottom nav
    "BottomNav",
    # Live timer
    "LiveTimer",
    # Animated labels
    "AnimatedLabel", "TypewriterLabel", "CountUpLabel",
    # Avatars
    "Avatar", "AVATAR_COLORS",
    # Empty state
    "EmptyState",
    # Skeleton
    "Skeleton", "SkeletonCard", "SkeletonList",
    # Tooltips
    "Tooltip",
    # Dialogs
    "BaseDialog", "AlertDialog", "ConfirmDialog",
    "PromptDialog", "ChoiceDialog", "BottomSheet",
    # Sheets
    "ActionSheet", "PickerSheet", "FilterSheet",
    "SortSheet", "ShareSheet",
    # Toasts
    "Toast", "ToastManager",
    # Confetti
    "Confetti",
    # Calendar
    "CalendarGrid",
    # Pickers
    "DatePicker", "TimePicker",
    # Scrollable
    "SmoothScrollFrame", "VirtualList", "ParallaxHeader",
    # Pull-to-refresh
    "PullToRefresh",
]
