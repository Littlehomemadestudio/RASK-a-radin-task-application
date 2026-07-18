"""
rask.ui.screens.templates_screen
===============================

Templates screen — full CRUD UI for quick-log templates.

Templates are pre-filled activity recipes (title, category, duration,
tags, shortcut) that the user can apply with a single tap.  This screen
lists every non-archived template, lets the user sort, search, use,
edit, duplicate, archive, and delete them.

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"قالب‌ها"`` with a ``"+ جدید"`` action button
    2. **Search bar** — full-text filter over title / category / tags
    3. **Sort bar** — segmented control: by name / by use count / by recent
    4. **Template list** — vertical stack of :class:`TemplateListItem`,
       each showing: title, category color stripe, duration, shortcut,
       use count, last used relative time
    5. **Empty state** — friendly illustration when no templates exist

Interactions
------------
* Tap a template — apply it (creates an activity via template_service.use)
* Long-press a template — open an :class:`ActionSheet` with options:
  Edit / Duplicate / Archive / Delete
* Swipe a template row — reveal delete button

Auto-refresh
------------
Subscribes to ``template.added`` / ``template.updated`` /
``template.deleted`` / ``template.used`` / ``template.archived`` /
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
from ...services import template_service, settings_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, FabButton, PillButton,
)
from ..widgets.cards import Card
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.inputs import SearchEntry
from ..widgets.list_items import TemplateListItem
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toggles import SegmentedControl
from ..widgets.sheets import ActionSheet
from ..widgets.dialogs import ConfirmDialog

__all__ = ["TemplatesScreen"]


# =============================================================================
# === Sort labels                                                            ===
# =============================================================================

SORT_BY_NAME_FA = "نام"
SORT_BY_USE_FA = "استفاده"
SORT_BY_RECENT_FA = "اخیر"
SORT_BY_NAME_EN = "Name"
SORT_BY_USE_EN = "Use"
SORT_BY_RECENT_EN = "Recent"


def _sort_labels(lang: str) -> List[str]:
    if lang == "fa":
        return [SORT_BY_NAME_FA, SORT_BY_USE_FA, SORT_BY_RECENT_FA]
    return [SORT_BY_NAME_EN, SORT_BY_USE_EN, SORT_BY_RECENT_EN]


def _sort_index(label: str, lang: str) -> int:
    labels = _sort_labels(lang)
    if label in labels:
        return labels.index(label)
    return 0


# =============================================================================
# === TemplatesScreen                                                        ===
# =============================================================================

class TemplatesScreen(ctk.CTkFrame):
    """Quick-log templates browser.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``open_template_dialog(template_id=None)``
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
        self._query: str = ""
        self._sort_idx: int = 1  # default: by use count
        self._template_items: List[ctk.CTkBaseClass] = []
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
            self, title=i18n.t("templates", self._lang),
            action_text=self._tr("newTemplate", "New template"),
            on_action=self._on_new_template,
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
            command=self._on_new_template, lang=self._lang,
        )
        self.after(100, self._place_fab)
        # Sections
        self._section_row = 0
        self._build_search_bar()
        self._build_sort_bar()
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

    def _build_search_bar(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._search = SearchEntry(
            section,
            placeholder=self._tr("searchTemplates", "Search templates…"),
            lang=self._lang, height=40,
            on_change=self._on_search_change,
            on_submit=self._on_search_submit,
        )
        self._search.grid(row=0, column=0, sticky="ew")

    def _build_sort_bar(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Label + segmented control
        sort_row = ctk.CTkFrame(section, fg_color="transparent")
        sort_row.grid(row=0, column=0, sticky="ew")
        sort_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            sort_row, text=self._tr("sortBy", "Sort by"),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                padx=(0, 8) if rtl else (0, 0))
        self._sort_seg = SegmentedControl(
            sort_row, values=_sort_labels(self._lang),
            lang=self._lang,
            on_change=self._on_sort_change, height=32,
        )
        self._sort_seg.grid(row=0, column=1, sticky="e" if rtl else "w")
        # Set initial
        try:
            self._sort_seg.value = _sort_labels(self._lang)[self._sort_idx]
        except Exception:
            pass

    def _build_list(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("allTemplates", "All templates"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        # Count label
        self._count_label = ctk.CTkLabel(
            section, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
            anchor="e" if rtl else "w",
        )
        self._count_label.grid(row=1, column=0, sticky="e" if rtl else "w",
                                pady=(0, config.SPACE_SM))
        # Items container
        self._list_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._list_frame.grid(row=2, column=0, sticky="ew")
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
            "template.added", "template.updated", "template.deleted",
            "template.used", "template.archived",
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
        """Rebuild the template list."""
        # Clear old items
        for child in self._list_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._template_items = []
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        # Fetch templates
        try:
            templates = template_service.list(include_archived=False)
        except Exception:
            templates = []
        # Apply search filter
        if self._query:
            q = self._query.lower().strip()
            templates = [
                t for t in templates
                if q in (t.get("title") or "").lower()
                or q in (t.get("name") or "").lower()
                or q in " ".join(t.get("tags") or []).lower()
                or q in (t.get("notes") or "").lower()
            ]
        # Apply sort
        templates = self._sort_templates(templates)
        # Update count
        try:
            count = len(templates)
            count_str = (i18n.to_fa_digits(str(count))
                          if self._lang == "fa" else str(count))
            total_str = self._tr("items", "items")
            self._count_label.configure(text=f"{count_str} {total_str}")
        except Exception:
            pass
        # Empty state
        if not templates:
            self._empty_state = EmptyState(
                self._list_frame, icon="plus",
                title=(self._tr("noTemplates", "No templates yet")
                       if not self._query
                       else self._tr("noMatches", "No matches")),
                subtitle=(self._tr("noTemplatesHint",
                                    "Create one to log activities faster")
                          if not self._query
                          else self._tr("tryOtherQuery",
                                        "Try a different search")),
                action_text=self._tr("newTemplate", "New template"),
                on_action=self._on_new_template,
                lang=self._lang,
            )
            self._empty_state.grid(row=0, column=0, sticky="ew",
                                    pady=config.SPACE_LG)
            return
        # Build items
        cats = self._category_map()
        for i, t in enumerate(templates):
            cat_id = t.get("category_id")
            cat = cats.get(cat_id) if cat_id else None
            item = TemplateListItem(
                self._list_frame,
                title=t.get("title") or t.get("name") or "—",
                duration_min=int(t.get("duration_min") or 0),
                shortcut=t.get("shortcut"),
                use_count=int(t.get("use_count") or 0),
                on_click=lambda tid=t.get("id"): self._on_tap(tid),
                on_delete=lambda tid=t.get("id"): self._on_delete(tid),
                lang=self._lang,
            )
            item.grid(row=i, column=0, sticky="ew",
                       pady=(0 if i == 0 else 4, 4))
            self._template_items.append(item)

    def _sort_templates(
        self, templates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if self._sort_idx == 0:
            # By name (alphabetical)
            return sorted(
                templates,
                key=lambda t: (t.get("title") or t.get("name") or "").lower(),
            )
        elif self._sort_idx == 1:
            # By use count (desc)
            return sorted(
                templates,
                key=lambda t: -int(t.get("use_count") or 0),
            )
        else:
            # By recent (last_used_iso desc)
            return sorted(
                templates,
                key=lambda t: t.get("last_used_iso") or "",
                reverse=True,
            )

    def _category_map(self) -> Dict[int, Dict[str, Any]]:
        try:
            cats = db.category_list()
            return {c["id"]: c for c in cats}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_search_change(self, value: str) -> None:
        self._query = value
        self._schedule_refresh()

    def _on_search_submit(self, value: str) -> None:
        self._query = value
        self.refresh()

    def _on_sort_change(self, label: str) -> None:
        self._sort_idx = _sort_index(label, self._lang)
        self.refresh()

    def _on_new_template(self) -> None:
        if self._app and hasattr(self._app, "open_template_dialog"):
            try:
                self._app.open_template_dialog()
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.template_dialog_requested")
        except Exception:
            pass

    def _on_tap(self, template_id: int) -> None:
        """Use the template — creates a new activity."""
        try:
            activity = template_service.use(template_id)
            self._show_toast(
                f"{self._tr('logged', 'Logged')}: "
                f"{activity.get('title') or '—'}")
        except KeyError:
            self._show_toast(self._tr("notFound", "Template not found"))
        except ValueError:
            self._show_toast(self._tr("archived", "Template is archived"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_long_press(self, template_id: int) -> None:
        """Open action sheet: Edit / Duplicate / Archive / Delete."""
        actions = [
            (self._tr("edit", "Edit"),
             lambda: self._on_edit(template_id)),
            (self._tr("duplicate", "Duplicate"),
             lambda: self._on_duplicate(template_id)),
            (self._tr("archive", "Archive"),
             lambda: self._on_archive(template_id)),
            (self._tr("delete", "Delete"),
             lambda: self._on_delete(template_id)),
        ]
        ActionSheet(
            self, title=self._tr("templateActions", "Template actions"),
            actions=actions, lang=self._lang,
            destructive=self._tr("delete", "Delete"),
        )

    def _on_edit(self, template_id: int) -> None:
        if self._app and hasattr(self._app, "open_template_dialog"):
            try:
                self._app.open_template_dialog(template_id=template_id)
            except Exception:
                pass

    def _on_duplicate(self, template_id: int) -> None:
        try:
            t = template_service.get(template_id)
            if not t:
                return
            new = template_service.add(
                name=f"{t.get('name') or ''} (copy)",
                title=t.get("title") or "",
                category_id=t.get("category_id"),
                duration_min=int(t.get("duration_min") or 0),
                notes=t.get("notes"),
                tags=t.get("tags") or [],
                shortcut=None,  # don't duplicate shortcut
            )
            self._show_toast(
                f"{self._tr('duplicated', 'Duplicated')}: "
                f"{new.get('title') or '—'}")
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_archive(self, template_id: int) -> None:
        try:
            template_service.archive(template_id)
            self._show_toast(self._tr("archived", "Archived"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_delete(self, template_id: int) -> None:
        dlg = ConfirmDialog(
            self, title=self._tr("deleteTemplate", "Delete template"),
            message=self._tr("deleteTemplateConfirm",
                              "Delete this template?"),
            yes_text=self._tr("delete", "Delete"),
            no_text=self._tr("cancel", "Cancel"),
            danger=True, lang=self._lang,
        )
        dlg.on_result(lambda ok: self._do_delete(template_id) if ok
                       else None)

    def _do_delete(self, template_id: int) -> None:
        try:
            template_service.delete(template_id)
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
    print("TemplatesScreen module: search + sort + list + actions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
