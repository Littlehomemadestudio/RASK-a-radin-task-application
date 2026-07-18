"""
rask.ui.screens.categories_screen
=================================

Categories screen — manage the user's activity categories.

Each category has: a key, a Persian + English name, a colour, an icon,
an order index, an archived flag, and a count of activities using it.

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"دسته‌ها"`` with a ``"+ جدید"`` action button
    2. **Active / Archived tabs** — SegmentedControl to switch between
       active and archived categories
    3. **List** — vertical stack of :class:`CategoryListItem`s, each
       showing: colour swatch, name (in current language), icon,
       activity count, archived toggle, edit and delete buttons
    4. **Empty state** — friendly illustration when no categories
    5. **FAB** — quick-add new category

Interactions
------------
* Tap a category — open the edit dialog
* Long-press a category — open :class:`ActionSheet`:
  Edit / Archive (or Unarchive) / Delete
* Delete requires confirmation: ``"این دسته و تمام فعالیت‌هایش حذف شوند؟"``

Auto-refresh
------------
Subscribes to ``category.added`` / ``category.updated`` /
``category.deleted`` / ``activity.added`` / ``activity.deleted`` /
``language.changed`` / ``data.imported`` / ``data.cleared``.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import event_bus, time_utils, jalali, helpers
from ...services import settings_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, FabButton, DangerButton,
)
from ..widgets.cards import Card
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.list_items import CategoryListItem
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toggles import SegmentedControl
from ..widgets.sheets import ActionSheet
from ..widgets.dialogs import ConfirmDialog

__all__ = ["CategoriesScreen"]


# =============================================================================
# === Tab labels                                                             ===
# =============================================================================

TAB_ACTIVE_FA = "فعال"
TAB_ARCHIVED_FA = "بایگانی"
TAB_ACTIVE_EN = "Active"
TAB_ARCHIVED_EN = "Archived"


def _tab_labels(lang: str) -> List[str]:
    if lang == "fa":
        return [TAB_ACTIVE_FA, TAB_ARCHIVED_FA]
    return [TAB_ACTIVE_EN, TAB_ARCHIVED_EN]


# =============================================================================
# === CategoriesScreen                                                       ===
# =============================================================================

class CategoriesScreen(ctk.CTkFrame):
    """Categories browser.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``open_category_dialog(category_id=None)``
            * ``show_toast(message)``
            * ``confirm_delete(message, on_confirm)``
    lang
        ``"fa"`` (default) or ``"en"``.
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._subscriptions: List[tuple] = []
        self._refresh_job: Optional[Any] = None
        self._refresh_pending: bool = False
        self._tab_idx: int = 0  # 0 = active, 1 = archived
        self._category_items: List[ctk.CTkBaseClass] = []
        self._empty_state: Optional[EmptyState] = None
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header
        self._header = Header(
            self, title=i18n.t("categories", self._lang)
            if i18n.t("categories", self._lang) != "categories"
            else (self._tr("categories", "Categories")),
            action_text=self._tr("newCategory", "New"),
            on_action=self._on_new_category,
            lang=self._lang, height=56,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        # Scrollable content
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # FAB
        self._fab = FabButton(
            self, icon_name="plus",
            command=self._on_new_category, lang=self._lang,
        )
        self.after(100, self._place_fab)
        # Sections
        self._section_row = 0
        self._build_tabs()
        self._build_list()

    def _place_fab(self) -> None:
        try:
            w = max(1, self.winfo_width())
            h = max(1, self.winfo_height())
            fab_size = config.FAB_SIZE
            rtl = i18n.is_rtl(self._lang)
            x = 20 if rtl else w - fab_size - 20
            y = h - fab_size - 80
            self._fab.place(x=x, y=y)
        except Exception:
            pass

    def _build_tabs(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._tab_seg = SegmentedControl(
            section, values=_tab_labels(self._lang),
            lang=self._lang,
            on_change=self._on_tab_change, height=36,
        )
        self._tab_seg.grid(row=0, column=0, sticky="ew")
        try:
            self._tab_seg.value = _tab_labels(self._lang)[self._tab_idx]
        except Exception:
            pass

    def _build_list(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Count label
        self._count_label = ctk.CTkLabel(
            section, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
            anchor="e" if rtl else "w",
        )
        self._count_label.grid(row=0, column=0, sticky="e" if rtl else "w",
                                pady=(0, config.SPACE_SM))
        self._list_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._list_frame.grid(row=1, column=0, sticky="ew")
        self._list_frame.grid_columnconfigure(0, weight=1)

    def _next_row(self) -> int:
        r = self._section_row
        self._section_row += 1
        return r

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        events = [
            "category.added", "category.updated", "category.deleted",
            "activity.added", "activity.updated", "activity.deleted",
            "language.changed",
            "data.imported", "data.cleared",
        ]
        for ev in events:
            try:
                bus.subscribe(ev, self._on_data_changed)
                self._subscriptions.append((ev, self._on_data_changed))
            except Exception:
                pass

    def _unsubscribe_events(self) -> None:
        bus = event_bus.bus
        for ev, cb in self._subscriptions:
            try:
                bus.unsubscribe(ev, cb)
            except Exception:
                pass
        self._subscriptions.clear()

    def _on_data_changed(self, *args: Any, **kwargs: Any) -> None:
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self._refresh_job = self.after(120, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the list for the active tab."""
        # Clear old items
        for child in self._list_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._category_items = []
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        # Fetch categories
        try:
            all_cats = db.category_list(include_archived=True)
        except Exception:
            all_cats = []
        # Filter by tab
        show_archived = (self._tab_idx == 1)
        cats = [c for c in all_cats
                if bool(c.get("archived", 0)) == show_archived]
        # Sort by order_index
        cats.sort(key=lambda c: int(c.get("order_index", 0) or 0))
        # Count label
        try:
            count = len(cats)
            count_str = (i18n.to_fa_digits(str(count))
                          if self._lang == "fa" else str(count))
            tab_word = (self._tr("active", "active")
                        if not show_archived
                        else self._tr("archived", "archived"))
            self._count_label.configure(
                text=f"{count_str} {self._tr('categories', 'categories')} "
                     f"({tab_word})")
        except Exception:
            pass
        # Empty state
        if not cats:
            self._empty_state = EmptyState(
                self._list_frame, icon="folder",
                title=(self._tr("noCategoriesArchived",
                                 "No archived categories")
                       if show_archived
                       else self._tr("noCategories",
                                      "No categories yet")),
                subtitle=(self._tr("archivedEmpty",
                                    "Archived categories will appear here")
                          if show_archived
                          else self._tr("noCategoriesHint",
                                         "Create one to organize activities")),
                action_text=(None if show_archived
                              else self._tr("newCategory", "New")),
                on_action=(None if show_archived
                            else self._on_new_category),
                lang=self._lang,
            )
            self._empty_state.grid(row=0, column=0, sticky="ew",
                                    pady=config.SPACE_LG)
            return
        # Build items
        for i, cat in enumerate(cats):
            name = (cat.get("name_fa") if self._lang == "fa"
                     else cat.get("name_en")) or "—"
            color = cat.get("color") or config.GOLD
            count = self._count_activities(cat.get("id"))
            item = CategoryListItem(
                self._list_frame,
                name=name, color=color, activity_count=count,
                on_click=lambda cid=cat.get("id"): self._on_tap(cid),
                on_delete=lambda cid=cat.get("id"): self._on_delete(cid),
                lang=self._lang,
            )
            item.grid(row=i, column=0, sticky="ew",
                       pady=(0 if i == 0 else 4, 4))
            self._category_items.append(item)

    def _count_activities(self, category_id: Optional[int]) -> int:
        if not category_id:
            return 0
        try:
            return int(db.activity_count(category_ids=[category_id]))
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_tab_change(self, label: str) -> None:
        labels = _tab_labels(self._lang)
        if label in labels:
            self._tab_idx = labels.index(label)
            self.refresh()

    def _on_new_category(self) -> None:
        if self._app and hasattr(self._app, "open_category_dialog"):
            try:
                self._app.open_category_dialog()
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.category_dialog_requested")
        except Exception:
            pass

    def _on_tap(self, category_id: int) -> None:
        if self._app and hasattr(self._app, "open_category_dialog"):
            try:
                self._app.open_category_dialog(category_id=category_id)
            except Exception:
                pass

    def _on_long_press(self, category_id: int) -> None:
        # Determine if archived
        try:
            cat = db.category_get(category_id)
            is_archived = bool(cat and cat.get("archived", 0))
        except Exception:
            is_archived = False
        if is_archived:
            actions = [
                (self._tr("edit", "Edit"),
                 lambda: self._on_tap(category_id)),
                (self._tr("unarchive", "Unarchive"),
                 lambda: self._on_unarchive(category_id)),
                (self._tr("delete", "Delete"),
                 lambda: self._on_delete(category_id)),
            ]
        else:
            actions = [
                (self._tr("edit", "Edit"),
                 lambda: self._on_tap(category_id)),
                (self._tr("archive", "Archive"),
                 lambda: self._on_archive(category_id)),
                (self._tr("delete", "Delete"),
                 lambda: self._on_delete(category_id)),
            ]
        ActionSheet(
            self, title=self._tr("categoryActions", "Category actions"),
            actions=actions, lang=self._lang,
            destructive=self._tr("delete", "Delete"),
        )

    def _on_archive(self, category_id: int) -> None:
        try:
            db.category_update(category_id, archived=1)
            self._show_toast(self._tr("archived", "Archived"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_unarchive(self, category_id: int) -> None:
        try:
            db.category_update(category_id, archived=0)
            self._show_toast(self._tr("unarchived", "Unarchived"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_delete(self, category_id: int) -> None:
        """Confirm before deleting — also deletes all activities in cat."""
        msg = (self._tr("deleteCategoryConfirm",
                         "Delete this category AND all its activities?")
               if self._lang == "en"
               else "این دسته و تمام فعالیت‌هایش حذف شوند؟")
        dlg = ConfirmDialog(
            self, title=self._tr("deleteCategory", "Delete category"),
            message=msg,
            yes_text=self._tr("delete", "Delete"),
            no_text=self._tr("cancel", "Cancel"),
            danger=True, lang=self._lang,
        )
        dlg.on_result(lambda ok: self._do_delete(category_id) if ok
                       else None)

    def _do_delete(self, category_id: int) -> None:
        try:
            # First delete all activities in this category
            try:
                conn = db.get_conn()
                conn.execute(
                    "UPDATE activities SET deleted_at = CURRENT_TIMESTAMP "
                    "WHERE category_id = ?", (category_id,))
                conn.commit()
            except Exception:
                pass
            # Then delete the category
            db.category_delete(category_id)
            self._show_toast(self._tr("deleted", "Deleted"))
        except Exception as exc:
            self._show_toast(str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _tr(self, fa: str, en: str) -> str:
        try:
            from ...i18n import t as _t
            v = _t(fa, self._lang)
            if v != fa:
                return v
        except Exception:
            pass
        return fa if self._lang == "fa" else en

    def _show_toast(self, message: str) -> None:
        if self._app and hasattr(self._app, "show_toast"):
            try:
                self._app.show_toast(message)
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.toast", {"message": message,
                                                "kind": "info"})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def destroy(self) -> None:  # type: ignore[override]
        self._unsubscribe_events()
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("CategoriesScreen module: tabs + list + archive/delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
