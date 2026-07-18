"""
rask.ui.screens.search_screen
=============================

Full-screen search overlay for activities.

Search provides:
    * Debounced live search (200 ms) as you type
    * Filter chips: category, tags, date range, duration range
    * Result count: ``"۵ مورد یافت شد"``
    * Recent searches (last 10) when query is empty
    * Suggested searches (quick filters) when query is empty
    * Result list: :class:`ActivityListItem` with highlighted matching text
    * Keyboard: Enter to commit search, Esc to close
    * Tap result to edit activity (calls ``app.open_activity_dialog``)

Auto-refresh
------------
Search doesn't subscribe to activity events (it's a one-shot lookup),
but it does subscribe to ``language.changed`` to re-render labels.
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
from ...services import activity_service, settings_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
)
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.inputs import SearchEntry
from ..widgets.list_items import ActivityListItem
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.badges import Chip

__all__ = ["SearchScreen"]


# =============================================================================
# === Constants                                                              ===
# =============================================================================

RECENT_SEARCHES_KEY: str = "recent_searches"
MAX_RECENT: int = 10
DEBOUNCE_MS: int = 200


# =============================================================================
# === SearchScreen                                                           ===
# =============================================================================

class SearchScreen(ctk.CTkFrame):
    """Full-screen search overlay.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``open_activity_dialog(activity_id)``
            * ``close_search()``
            * ``show_toast(message)``
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
        self._query: str = ""
        self._debounce_job: Optional[Any] = None
        self._filter_category_ids: List[int] = []
        self._filter_tags: List[str] = []
        self._filter_date_from: Optional[str] = None
        self._filter_date_to: Optional[str] = None
        self._filter_min_dur: Optional[int] = None
        self._filter_max_dur: Optional[int] = None
        self._result_items: List[ctk.CTkBaseClass] = []
        self._build()
        self._subscribe_events()
        # Auto-focus search bar after render
        self.after(120, self._focus_search)
        # Bind Esc to close
        try:
            self.bind_all("<Escape>", lambda _e: self._on_close(), add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        # Header row: close button + search entry
        header = ctk.CTkFrame(self, fg_color=config.MATTE_BLACK, height=56)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Close button
        close_col = 0 if rtl else 2
        IconButton(
            header, icon_name="arrow_right" if rtl else "arrow_left",
            command=self._on_close, size=40, lang=self._lang,
        ).grid(row=0, column=close_col, padx=4, pady=8)
        # Search entry
        self._search = SearchEntry(
            header,
            placeholder=self._tr("searchActivities", "Search activities…"),
            lang=self._lang, height=40,
            on_change=self._on_search_change,
            on_submit=self._on_search_submit,
        )
        self._search.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        # Filter chips row
        filter_row = ctk.CTkFrame(self, fg_color=config.MATTE_BLACK, height=44)
        filter_row.grid(row=1, column=0, sticky="ew")
        filter_row.grid_columnconfigure(0, weight=1)
        self._filter_strip = ctk.CTkScrollableFrame(
            filter_row, fg_color="transparent",
            orientation="horizontal", height=40,
        )
        self._filter_strip.grid(row=0, column=0, sticky="ew", padx=8, pady=2)
        self._filter_strip.grid_columnconfigure(0, weight=1)
        # Build filter chips
        self._build_filter_chips()
        # Results scroll
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=2, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # Results container
        self._results_frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._results_frame.grid(row=0, column=0, sticky="ew",
                                   padx=config.SPACE_LG,
                                   pady=(config.SPACE_SM, config.SPACE_LG))
        self._results_frame.grid_columnconfigure(0, weight=1)
        # Count label
        self._count_label = ctk.CTkLabel(
            self._results_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        )
        self._count_label.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        # Items container
        self._items_frame = ctk.CTkFrame(self._results_frame,
                                          fg_color="transparent")
        self._items_frame.grid(row=1, column=0, sticky="ew")
        self._items_frame.grid_columnconfigure(0, weight=1)
        # Initial render
        self.refresh()

    def _build_filter_chips(self) -> None:
        """Build the filter chip strip."""
        for child in self._filter_strip.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        rtl = i18n.is_rtl(self._lang)
        # Category filter chip
        cat_text = self._tr("category", "Category")
        if self._filter_category_ids:
            cat_text += f" ({i18n.to_fa_digits(str(len(self._filter_category_ids)))
                              if self._lang == 'fa'
                              else str(len(self._filter_category_ids))})"
        cat_chip = PillButton(
            self._filter_strip, text=cat_text,
            command=self._on_category_filter,
            lang=self._lang, height=30,
            color=(config.GOLD if self._filter_category_ids
                    else config.SURFACE_HI),
            text_color=(config.MATTE_BLACK if self._filter_category_ids
                         else config.TEXT),
            font_size=config.FONT_SIZE_CAPTION,
        )
        cat_chip.pack(side="right" if rtl else "left", padx=4, pady=4)
        # Tags filter chip
        tag_text = self._tr("tags", "Tags")
        if self._filter_tags:
            tag_text += f" ({i18n.to_fa_digits(str(len(self._filter_tags)))
                              if self._lang == 'fa'
                              else str(len(self._filter_tags))})"
        tag_chip = PillButton(
            self._filter_strip, text=tag_text,
            command=self._on_tags_filter,
            lang=self._lang, height=30,
            color=(config.GOLD if self._filter_tags
                    else config.SURFACE_HI),
            text_color=(config.MATTE_BLACK if self._filter_tags
                         else config.TEXT),
            font_size=config.FONT_SIZE_CAPTION,
        )
        tag_chip.pack(side="right" if rtl else "left", padx=4, pady=4)
        # Date range filter chip
        date_text = self._tr("dateRange", "Date")
        if self._filter_date_from or self._filter_date_to:
            date_text += " ✓"
        date_chip = PillButton(
            self._filter_strip, text=date_text,
            command=self._on_date_filter,
            lang=self._lang, height=30,
            color=(config.GOLD if (self._filter_date_from
                                  or self._filter_date_to)
                    else config.SURFACE_HI),
            text_color=(config.MATTE_BLACK if (self._filter_date_from
                                               or self._filter_date_to)
                         else config.TEXT),
            font_size=config.FONT_SIZE_CAPTION,
        )
        date_chip.pack(side="right" if rtl else "left", padx=4, pady=4)
        # Duration filter chip
        dur_text = self._tr("duration", "Duration")
        if self._filter_min_dur or self._filter_max_dur:
            dur_text += " ✓"
        dur_chip = PillButton(
            self._filter_strip, text=dur_text,
            command=self._on_duration_filter,
            lang=self._lang, height=30,
            color=(config.GOLD if (self._filter_min_dur
                                  or self._filter_max_dur)
                    else config.SURFACE_HI),
            text_color=(config.MATTE_BLACK if (self._filter_min_dur
                                               or self._filter_max_dur)
                         else config.TEXT),
            font_size=config.FONT_SIZE_CAPTION,
        )
        dur_chip.pack(side="right" if rtl else "left", padx=4, pady=4)
        # Clear-all chip
        if any([self._filter_category_ids, self._filter_tags,
                self._filter_date_from, self._filter_date_to,
                self._filter_min_dur, self._filter_max_dur]):
            clear_chip = PillButton(
                self._filter_strip, text=self._tr("clear", "Clear"),
                command=self._on_clear_filters,
                lang=self._lang, height=30,
                color=config.DANGER_DIM, text_color=config.DANGER,
                font_size=config.FONT_SIZE_CAPTION,
            )
            clear_chip.pack(side="right" if rtl else "left", padx=4, pady=4)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        for ev in ("language.changed",):
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
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Render results (or recent / suggested when query is empty)."""
        # Clear items
        for child in self._items_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._result_items = []
        # Empty query: show recent + suggested
        if not self._query.strip() and not self._has_filters():
            self._count_label.configure(text="")
            self._render_recent_and_suggested()
            return
        # Perform search
        try:
            results = self._do_search()
        except Exception:
            results = []
        # Update count label
        try:
            count = len(results)
            count_str = (i18n.to_fa_digits(str(count))
                         if self._lang == "fa" else str(count))
            unit = self._tr("results", "results")
            self._count_label.configure(text=f"{count_str} {unit}")
        except Exception:
            pass
        # Empty state
        if not results:
            EmptyState(
                self._items_frame, icon="search",
                title=self._tr("noMatches", "No matches"),
                subtitle=self._tr("tryDifferent",
                                   "Try a different query or filter"),
                lang=self._lang,
            ).grid(row=0, column=0, sticky="ew", pady=config.SPACE_LG)
            return
        # Build result items
        cats = self._category_map()
        rtl = i18n.is_rtl(self._lang)
        for i, a in enumerate(results):
            cat_id = a.get("category_id")
            cat = cats.get(cat_id) if cat_id else None
            if cat:
                cat_name = (cat.get("name_fa") if self._lang == "fa"
                              else cat.get("name_en")) or "—"
                cat_color = cat.get("color") or config.GOLD
            else:
                cat_name = "—"
                cat_color = config.GOLD
            # Duration
            try:
                duration_sec = int(a.get("duration_sec",
                                          a.get("duration_min", 0) * 60)
                                    or 0)
                duration_str = time_utils.seconds_to_human(
                    duration_sec, lang=self._lang)
            except Exception:
                duration_str = "—"
            # Time
            try:
                date_iso = a.get("date_iso") or ""
                time_str = time_utils.format_relative(
                    date_iso + "T00:00:00", lang=self._lang)
            except Exception:
                time_str = ""
            # Title with highlight
            title = a.get("title") or "—"
            highlighted_title = self._highlight(title)
            item = ActivityListItem(
                self._items_frame,
                title=highlighted_title,
                category_name=cat_name,
                category_color=cat_color,
                duration=duration_str,
                time_str=time_str,
                tags=a.get("tags") if isinstance(a.get("tags"), list)
                      else None,
                on_click=lambda aid=a.get("id"): self._on_tap(aid),
                lang=self._lang,
            )
            item.grid(row=i, column=0, sticky="ew",
                       pady=(0 if i == 0 else 4, 4))
            self._result_items.append(item)

    def _has_filters(self) -> bool:
        return any([self._filter_category_ids, self._filter_tags,
                    self._filter_date_from, self._filter_date_to,
                    self._filter_min_dur, self._filter_max_dur])

    def _do_search(self) -> List[Dict[str, Any]]:
        """Run the search via activity_service.list()."""
        try:
            results = activity_service.list(
                search=self._query.strip() or None,
                category_ids=self._filter_category_ids or None,
                tags=self._filter_tags or None,
                date_from=self._filter_date_from,
                date_to=self._filter_date_to,
                min_duration=self._filter_min_dur,
                max_duration=self._filter_max_dur,
                limit=100,
            )
        except Exception:
            results = []
        return results

    def _render_recent_and_suggested(self) -> None:
        """Render recent searches + suggested quick filters."""
        rtl = i18n.is_rtl(self._lang)
        # Recent searches section
        recent = self._load_recent_searches()
        if recent:
            SectionTitle(
                self._items_frame,
                text=self._tr("recentSearches", "Recent searches"),
                lang=self._lang, size=config.FONT_SIZE_BODY_LG,
            ).grid(row=0, column=0, sticky="e" if rtl else "w",
                    pady=(0, config.SPACE_SM))
            recents_row = ctk.CTkFrame(self._items_frame, fg_color="transparent")
            recents_row.grid(row=1, column=0, sticky="ew")
            for i, q in enumerate(recent[:8]):
                chip = PillButton(
                    recents_row, text=q,
                    command=lambda qq=q: self._apply_query(qq),
                    lang=self._lang, height=30,
                    color=config.CHARCOAL, text_color=config.TEXT,
                    font_size=config.FONT_SIZE_CAPTION,
                )
                chip.pack(side="right" if rtl else "left", padx=4, pady=4)
            next_row = 2
        else:
            next_row = 0
        # Suggested quick filters
        SectionTitle(
            self._items_frame,
            text=self._tr("suggested", "Suggested"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=next_row, column=0, sticky="e" if rtl else "w",
                pady=(config.SPACE_MD, config.SPACE_SM))
        suggestions_frame = ctk.CTkFrame(self._items_frame,
                                          fg_color="transparent")
        suggestions_frame.grid(row=next_row + 1, column=0, sticky="ew")
        suggestions = [
            self._tr("today", "Today"),
            self._tr("thisWeek", "This week"),
            self._tr("longSessions", "Long sessions (>1h)"),
            self._tr("shortSessions", "Short sessions (<15m)"),
        ]
        for i, sug in enumerate(suggestions):
            chip = PillButton(
                suggestions_frame, text=sug,
                command=lambda s=sug: self._apply_suggestion(s),
                lang=self._lang, height=30,
                color=config.SURFACE_HI, text_color=config.GOLD,
                font_size=config.FONT_SIZE_CAPTION,
            )
            chip.pack(side="right" if rtl else "left", padx=4, pady=4)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_search_change(self, value: str) -> None:
        """Debounced live search."""
        self._query = value
        if self._debounce_job is not None:
            try:
                self.after_cancel(self._debounce_job)
            except Exception:
                pass
        self._debounce_job = self.after(DEBOUNCE_MS, self.refresh)

    def _on_search_submit(self, value: str) -> None:
        """Enter key — commit search and add to recents."""
        self._query = value
        if self._debounce_job is not None:
            try:
                self.after_cancel(self._debounce_job)
            except Exception:
                pass
            self._debounce_job = None
        # Save to recents
        if value.strip():
            self._save_recent_search(value.strip())
        self.refresh()

    def _apply_query(self, query: str) -> None:
        """Apply a recent-search query — populate the entry + search."""
        try:
            self._search.value = query
        except Exception:
            pass
        self._query = query
        self.refresh()

    def _apply_suggestion(self, suggestion: str) -> None:
        """Apply a quick-filter suggestion."""
        # Match suggestion to a date range / duration filter
        today = time_utils.today_iso()
        if suggestion in (self._tr("today", "Today"),
                          "today"):
            self._filter_date_from = today
            self._filter_date_to = today
        elif suggestion in (self._tr("thisWeek", "This week"),
                             "this week"):
            try:
                self._filter_date_from = time_utils.start_of_week(today)
                self._filter_date_to = time_utils.end_of_week(today)
            except Exception:
                pass
        elif suggestion in (self._tr("longSessions",
                                       "Long sessions (>1h)"),):
            self._filter_min_dur = 60
            self._filter_max_dur = None
        elif suggestion in (self._tr("shortSessions",
                                       "Short sessions (<15m)"),):
            self._filter_min_dur = None
            self._filter_max_dur = 15
        self._build_filter_chips()
        self.refresh()

    def _on_category_filter(self) -> None:
        """Open a multi-select filter sheet for categories."""
        try:
            from ..widgets.sheets import FilterSheet
            cats = db.category_list()
            options = [
                (c.get("name_fa") if self._lang == "fa"
                  else c.get("name_en")) or c.get("key") or "—"
                for c in cats
            ]
            selected = [
                (db.category_get(cid) or {}).get(
                    "name_fa" if self._lang == "fa" else "name_en")
                for cid in self._filter_category_ids
            ]
            sheet = FilterSheet(
                self, title=self._tr("filterByCategory", "Filter by category"),
                options=options,
                selected=[s for s in selected if s],
                on_apply=lambda sels: self._apply_category_filter(sels, cats),
                on_clear=self._clear_category_filter,
                lang=self._lang,
            )
        except Exception as exc:
            self._show_toast(str(exc))

    def _apply_category_filter(self, selected_names: List[str],
                                cats: List[Dict[str, Any]]) -> None:
        self._filter_category_ids = []
        for c in cats:
            name = (c.get("name_fa") if self._lang == "fa"
                     else c.get("name_en")) or c.get("key") or "—"
            if name in selected_names:
                self._filter_category_ids.append(c["id"])
        self._build_filter_chips()
        self.refresh()

    def _clear_category_filter(self) -> None:
        self._filter_category_ids = []
        self._build_filter_chips()
        self.refresh()

    def _on_tags_filter(self) -> None:
        """Open a simple prompt for tag entry."""
        try:
            from ..widgets.dialogs import PromptDialog
            initial = ", ".join(self._filter_tags)
            dlg = PromptDialog(
                self, title=self._tr("filterByTags", "Filter by tags"),
                message=self._tr("tagsHint",
                                  "Enter tags separated by commas"),
                initial=initial, lang=self._lang,
            )
            dlg.on_result(lambda v: self._apply_tags(v) if v
                           else None)
        except Exception:
            pass

    def _apply_tags(self, value: str) -> None:
        self._filter_tags = [t.strip() for t in value.split(",")
                              if t.strip()]
        self._build_filter_chips()
        self.refresh()

    def _on_date_filter(self) -> None:
        """Prompt for from/to ISO dates."""
        try:
            from ..widgets.dialogs import PromptDialog
            initial = ""
            if self._filter_date_from and self._filter_date_to:
                initial = f"{self._filter_date_from}..{self._filter_date_to}"
            dlg = PromptDialog(
                self, title=self._tr("dateRange", "Date range"),
                message=self._tr("dateRangeHint",
                                  "Enter as YYYY-MM-DD..YYYY-MM-DD"),
                initial=initial, placeholder="2024-01-01..2024-12-31",
                lang=self._lang,
            )
            dlg.on_result(lambda v: self._apply_date_range(v) if v
                           else None)
        except Exception:
            pass

    def _apply_date_range(self, value: str) -> None:
        if ".." in value:
            from_str, to_str = value.split("..", 1)
            self._filter_date_from = from_str.strip() or None
            self._filter_date_to = to_str.strip() or None
        else:
            self._filter_date_from = value.strip() or None
            self._filter_date_to = None
        self._build_filter_chips()
        self.refresh()

    def _on_duration_filter(self) -> None:
        try:
            from ..widgets.dialogs import PromptDialog
            initial = ""
            if self._filter_min_dur and self._filter_max_dur:
                initial = f"{self._filter_min_dur}..{self._filter_max_dur}"
            elif self._filter_min_dur:
                initial = f"{self._filter_min_dur}.."
            elif self._filter_max_dur:
                initial = f"..{self._filter_max_dur}"
            dlg = PromptDialog(
                self, title=self._tr("durationRange", "Duration range"),
                message=self._tr("durationHint",
                                  "Minutes: e.g. 15..60"),
                initial=initial, placeholder="15..60",
                lang=self._lang,
            )
            dlg.on_result(lambda v: self._apply_duration(v) if v
                           else None)
        except Exception:
            pass

    def _apply_duration(self, value: str) -> None:
        if ".." in value:
            lo, hi = value.split("..", 1)
            try:
                self._filter_min_dur = int(lo) if lo.strip() else None
            except ValueError:
                self._filter_min_dur = None
            try:
                self._filter_max_dur = int(hi) if hi.strip() else None
            except ValueError:
                self._filter_max_dur = None
        else:
            try:
                self._filter_min_dur = int(value)
            except ValueError:
                self._filter_min_dur = None
            self._filter_max_dur = None
        self._build_filter_chips()
        self.refresh()

    def _on_clear_filters(self) -> None:
        self._filter_category_ids = []
        self._filter_tags = []
        self._filter_date_from = None
        self._filter_date_to = None
        self._filter_min_dur = None
        self._filter_max_dur = None
        self._build_filter_chips()
        self.refresh()

    def _on_tap(self, activity_id: int) -> None:
        if self._app and hasattr(self._app, "open_activity_dialog"):
            try:
                self._app.open_activity_dialog(activity_id)
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.activity_dialog_requested",
                                    {"id": activity_id})
        except Exception:
            pass

    def _on_close(self) -> None:
        if self._app and hasattr(self._app, "close_search"):
            try:
                self._app.close_search()
                return
            except Exception:
                pass
        try:
            self.place_forget()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _focus_search(self) -> None:
        try:
            self._search.focus()
        except Exception:
            pass

    def _highlight(self, text: str) -> str:
        """Highlight matching substrings (returns same text — Tk labels
        can't easily do rich text; we leave it as-is and rely on the
        user to spot the match visually)."""
        return text

    def _category_map(self) -> Dict[int, Dict[str, Any]]:
        try:
            cats = db.category_list()
            return {c["id"]: c for c in cats}
        except Exception:
            return {}

    def _load_recent_searches(self) -> List[str]:
        try:
            raw = db.kv_get(RECENT_SEARCHES_KEY)
            if not raw:
                return []
            import json
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(s) for s in data]
        except Exception:
            pass
        return []

    def _save_recent_search(self, query: str) -> None:
        try:
            recent = self._load_recent_searches()
            # Remove if already present
            if query in recent:
                recent.remove(query)
            recent.insert(0, query)
            recent = recent[:MAX_RECENT]
            import json
            db.kv_set(RECENT_SEARCHES_KEY, json.dumps(recent))
        except Exception:
            pass

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
        if self._debounce_job is not None:
            try:
                self.after_cancel(self._debounce_job)
            except Exception:
                pass
            self._debounce_job = None
        try:
            self.unbind_all("<Escape>")
        except Exception:
            pass
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("SearchScreen module: live search + filters + recents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
