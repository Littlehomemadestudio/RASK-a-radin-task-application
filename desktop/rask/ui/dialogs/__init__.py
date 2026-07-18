"""
rask.ui.dialogs
===============

Modal dialog library for the Rask desktop application.

Every dialog in this package is a modal popup that overlays the current
screen.  They are built on top of :class:`rask.ui.widgets.dialogs.BaseDialog`
and :class:`rask.ui.widgets.dialogs.BottomSheet`, so they inherit:

  * Gold-on-dark theme styling
  * RTL-aware layout when ``lang="fa"``
  * Smooth entrance / exit animations (200-300ms ease-out)
  * ESC-to-close (with confirmation if the form is dirty)
  * Click-outside-to-close (configurable per dialog)
  * Drag-to-dismiss for bottom sheets
  * A ``.result`` attribute for synchronous-style usage
  * An ``on_result(callback)`` fluent API for async usage

Quick start
-----------
>>> from rask.ui.dialogs import QuickLogDialog, GoalDialog
>>> dlg = QuickLogDialog(root, lang="fa")
>>> dlg.on_result(lambda r: print("saved", r))

Dialog catalogue
----------------
``QuickLogDialog``       — bottom-sheet quick activity logger (FAB tap)
``EditActivityDialog``   — modal for editing an existing activity
``GoalDialog``           — create / edit a daily/weekly/monthly goal
``TemplateDialog``       — create / edit a quick-log template
``ReminderDialog``       — create / edit a scheduled reminder
``CategoryDialog``       — create / edit a category
``PinSetupDialog``       — set up a new 4-digit PIN (two-step flow)
``BackupDialog``         — encrypted backup creation / restore
``ExportDialog``         — export activities to PDF/CSV/JSON/PNG
``FilterDialog``         — bottom-sheet activity filter UI
``CompareDialog``        — compare two periods side-by-side
``VoiceDialog``          — speech-to-text voice input modal
``ConfirmDialog``        — custom-styled confirmation (polished variant)
``OnboardingDialog``     — first-launch onboarding flow

All dialogs respect the user's current language (``settings_service``)
and Persian-digit conversion (``i18n.to_fa_digits``).
"""
from __future__ import annotations

# Dialog primitives come from the widgets package — re-exported here for
# convenience so callers can do `from rask.ui.dialogs import BaseDialog`.
from ..widgets.dialogs import BaseDialog, BottomSheet

# Domain-specific dialogs
from .confirm_dialog import ConfirmDialog
from .quick_log_dialog import QuickLogDialog
from .edit_activity_dialog import EditActivityDialog
from .goal_dialog import GoalDialog
from .template_dialog import TemplateDialog
from .reminder_dialog import ReminderDialog
from .category_dialog import CategoryDialog
from .pin_setup_dialog import PinSetupDialog
from .backup_dialog import BackupDialog
from .export_dialog import ExportDialog
from .filter_dialog import FilterDialog
from .compare_dialog import CompareDialog
from .voice_dialog import VoiceDialog
from .onboarding_dialog import OnboardingDialog

__all__ = [
    # Bases
    "BaseDialog", "BottomSheet",
    # Domain dialogs
    "QuickLogDialog",
    "EditActivityDialog",
    "GoalDialog",
    "TemplateDialog",
    "ReminderDialog",
    "CategoryDialog",
    "PinSetupDialog",
    "BackupDialog",
    "ExportDialog",
    "FilterDialog",
    "CompareDialog",
    "VoiceDialog",
    "ConfirmDialog",
    "OnboardingDialog",
]

# -----------------------------------------------------------------------------
# Convenience factory: open a dialog by class name from a string.
# Useful for command palettes and keyboard shortcuts.
# -----------------------------------------------------------------------------

_DIALOG_REGISTRY: dict = {
    "quick_log": QuickLogDialog,
    "edit_activity": EditActivityDialog,
    "goal": GoalDialog,
    "template": TemplateDialog,
    "reminder": ReminderDialog,
    "category": CategoryDialog,
    "pin_setup": PinSetupDialog,
    "backup": BackupDialog,
    "export": ExportDialog,
    "filter": FilterDialog,
    "compare": CompareDialog,
    "voice": VoiceDialog,
    "confirm": ConfirmDialog,
    "onboarding": OnboardingDialog,
}


def get_dialog_class(name: str):
    """Look up a dialog class by short name.

    Example
    -------
    >>> cls = get_dialog_class("goal")
    >>> dlg = cls(parent, lang="fa")
    """
    return _DIALOG_REGISTRY.get(name)


def available_dialogs() -> list:
    """Return a sorted list of registered dialog short-names."""
    return sorted(_DIALOG_REGISTRY.keys())
