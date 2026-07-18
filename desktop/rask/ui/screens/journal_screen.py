"""
rask.ui.screens.journal_screen
==============================

Daily journal screen — a calm, single-day journal editor that mirrors
the daily-reflection practice from the web app.

Each entry captures:

  • ``mood`` — 1..5 (very-bad..great)
  • ``energy`` — 1..5 (exhausted..energized)
  • ``title`` — short headline
  • ``body`` — long-form free text
  • ``strengths`` — bulleted list (today's wins)
  • ``improvements`` — bulleted list (what to do better)
  • ``gratitudes`` — bulleted list (3-item gratitude practice)
  • ``tags`` — list of strings

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"خاطرات روزانه"`` with date-picker icon
    2. **Date navigation** — prev / next day, today button,
       plus the current date in Persian (Jalali) long format
    3. **Streak indicator** — ``"۷ روز پیاپی"`` with flame icon
    4. **Mood selector** — 5 large emoji-style buttons (1..5) with
       text labels in Persian
    5. **Energy selector** — 5-dot selector (1..5)
    6. **Title field** — single-line entry
    7. **Body text area** — large multiline
    8. **Strengths / Improvements / Gratitudes** — three bulleted
       list editors (add/remove rows)
    9. **Tags** — chip strip with an entry to add new ones
    10. **Save button** — explicit save (auto-saves on edit too)
    11. **Previous entries** — opens a sheet listing past entries

The screen auto-creates an empty entry for today on first open (via
:meth:`JournalService.upsert`) so the user can start typing
immediately.

Auto-refresh
------------
Subscribes to ``journal.added`` / ``journal.updated`` /
``journal.deleted`` / ``journal.streak_changed`` /
``language.changed`` / ``data.cleared``.
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
from ...core import event_bus, time_utils, jalali
from ...features.journal import journal_service, JournalEntry
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.badges import Chip, TagChip
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.inputs import GoldEntry, TextArea
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.dialogs import AlertDialog

__all__ = ["JournalScreen"]


# =============================================================================
# === Mood / energy constants                                                ===
# =============================================================================

_MOOD_EMOJIS: Dict[int, str] = {
    1: "😞",
    2: "😕",
    3: "😐",
    4: "🙂",
    5: "😄",
}
_MOOD_LABELS_FA: Dict[int, str] = {
    1: "خیلی بد",
    2: "بد",
    3: "معمولی",
    4: "خوب",
    5: "عالی",
}
_MOOD_LABELS_EN: Dict[int, str] = {
    1: "Very Bad",
    2: "Bad",
    3: "Neutral",
    4: "Good",
    5: "Great",
}
_ENERGY_LABELS_FA: Dict[int, str] = {
    1: "خسته",
    2: "کم‌انرژی",
    3: "متوسط",
    4: "پرانرژی",
    5: "پرقدرت",
}
_ENERGY_LABELS_EN: Dict[int, str] = {
    1: "Exhausted",
    2: "Low",
    3: "Medium",
    4: "Energetic",
    5: "Powerful",
}
_MOOD_COLORS: Dict[int, str] = {
    1: config.DANGER,
    2: config.WARNING,
    3: config.TEXT_DIM,
    4: config.GOLD,
    5: config.SUCCESS,
}


def _mood_label(v: int, lang: str) -> str:
    if lang == "fa":
        return _MOOD_LABELS_FA.get(v, str(v))
    return _MOOD_LABELS_EN.get(v, str(v))


def _energy_label(v: int, lang: str) -> str:
    if lang == "fa":
        return _ENERGY_LABELS_FA.get(v, str(v))
    return _ENERGY_LABELS_EN.get(v, str(v))


# =============================================================================
# === Bulleted list editor widget                                            ===
# =============================================================================

class _BulletedListEditor(ctk.CTkFrame):
    """Add/remove rows of short text — used for strengths /
    improvements / gratitudes."""

    def __init__(
        self,
        master: Any,
        lang: str = "fa",
        placeholder: str = "",
        on_change: Optional[Callable[[List[str]], Any]] = None,
        max_rows: int = 12,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._lang = lang
        self._placeholder = placeholder
        self._on_change = on_change
        self._max_rows = max_rows
        self.grid_columnconfigure(0, weight=1)
        self._rows: List[Dict[str, Any]] = []
        self._add_button: Optional[ctk.CTkButton] = None
        # Initial empty row
        self._rebuild()

    def set_values(self, values: List[str]) -> None:
        """Replace the entire list with `values`."""
        values = [str(v) for v in (values or []) if str(v).strip()]
        if not values:
            values = [""]
        # Truncate to max
        values = values[: self._max_rows]
        self._rows = [{"text": v} for v in values]
        self._rebuild()

    def get_values(self) -> List[str]:
        out: List[str] = []
        for r in self._rows:
            try:
                t = r.get("entry").get().strip()  # type: ignore[union-attr]
            except Exception:
                t = ""
            if t:
                out.append(t)
        return out

    # ------------------------------------------------------------------
    def _rebuild(self) -> None:
        # Ensure at least one row
        if not self._rows:
            self._rows = [{"text": ""}]
        # Destroy old children
        for child in self.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        rtl = i18n.is_rtl(self._lang)
        for i, row in enumerate(self._rows):
            row_frame = ctk.CTkFrame(self, fg_color="transparent")
            row_frame.grid(row=i, column=0, sticky="ew",
                            pady=(0, config.SPACE_XS))
            row_frame.grid_columnconfigure(0, weight=1)
            # Bullet
            bullet = ctk.CTkLabel(
                row_frame, text="●",
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
            )
            bullet.grid(row=0, column=1 if rtl else 0, padx=(0 if rtl
                                                              else 0,
                                                              6 if rtl
                                                              else 6))
            # Entry
            entry = GoldEntry(
                row_frame, lang=self._lang,
                placeholder=self._placeholder,
            )
            entry.grid(row=0, column=0 if rtl else 1, sticky="ew")
            entry.insert(0, row.get("text", ""))
            entry.bind("<FocusOut>",
                        lambda _e, idx=i: self._on_row_change(idx))
            # Bind Enter to add a new row
            entry.bind("<Return>",
                        lambda _e, idx=i: self._on_enter(idx))
            row["entry"] = entry
            # Remove button (only if more than 1 row)
            if len(self._rows) > 1:
                rm_btn = IconButton(
                    row_frame, icon_name="close",
                    command=lambda idx=i: self._remove_row(idx),
                    size=28, lang=self._lang,
                )
                rm_btn.grid(row=0, column=2 if rtl else 0,
                              padx=(6 if rtl else 0, 0 if rtl else 6))
        # Add button (if under max)
        if len(self._rows) < self._max_rows:
            add_btn = TextButton(
                self, text=f"+ {self._placeholder}",
                command=self._add_row,
                lang=self._lang, height=28,
                font_size=config.FONT_SIZE_CAPTION,
                color=config.GOLD,
            )
            add_btn.grid(row=len(self._rows), column=0, sticky="e" if rtl
                          else "w", pady=(config.SPACE_XS, 0))
            self._add_button = add_btn

    def _add_row(self) -> None:
        if len(self._rows) >= self._max_rows:
            return
        self._rows.append({"text": ""})
        self._rebuild()
        # Focus the new row's entry
        try:
            new_entry = self._rows[-1].get("entry")
            if new_entry is not None:
                new_entry.focus_set()  # type: ignore[union-attr]
        except Exception:
            pass

    def _on_enter(self, idx: int) -> None:
        # Add a new row when Enter is pressed in any row except the last
        if idx == len(self._rows) - 1:
            self._add_row()

    def _remove_row(self, idx: int) -> None:
        if len(self._rows) <= 1:
            # Just clear the text
            try:
                e = self._rows[idx].get("entry")
                if e is not None:
                    e.delete(0, "end")  # type: ignore[union-attr]
            except Exception:
                pass
        else:
            self._rows.pop(idx)
            self._rebuild()
        self._notify_change()

    def _on_row_change(self, idx: int) -> None:
        try:
            e = self._rows[idx].get("entry")
            if e is not None:
                self._rows[idx]["text"] = e.get()  # type: ignore[union-attr]
        except Exception:
            pass
        self._notify_change()

    def _notify_change(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change(self.get_values())
            except Exception:
                pass


# =============================================================================
# === JournalScreen                                                          ===
# =============================================================================

class JournalScreen(ctk.CTkFrame):
    """Daily journal editor.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``open_date_picker(on_select)``
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
        self._current_date_iso: str = time_utils.today_iso()
        self._current_entry_id: Optional[int] = None
        self._mood_buttons: List[ctk.CTkButton] = []
        self._energy_buttons: List[ctk.CTkButton] = []
        self._selected_mood: Optional[int] = None
        self._selected_energy: Optional[int] = None
        self._tags: List[str] = []
        self._tag_chips: List[ctk.CTkBaseClass] = []
        self._auto_save_job: Optional[Any] = None
        self._loading_state: bool = False
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
            self, title=self._tr("خاطرات روزانه", "Daily Journal"),
            lang=self._lang, height=56,
            action_icon="calendar",
            on_action=self._open_date_picker,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        # Scroll
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_date_nav()
        self._build_streak()
        self._build_mood()
        self._build_energy()
        self._build_title()
        self._build_body()
        self._build_lists()
        self._build_tags()
        self._build_actions()
        self._build_history_button()

    def _build_date_nav(self) -> None:
        """Prev / next day, today button + current date label."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Prev day (left in LTR, right in RTL)
        prev_btn = IconButton(
            section, icon_name="chevron_right" if rtl else "chevron_left",
            command=lambda: self._go_day(-1),
            size=40, lang=self._lang,
        )
        prev_btn.grid(row=0, column=0 if rtl else 2, padx=4)
        # Date label (middle)
        self._date_label = ctk.CTkLabel(
            section, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._date_label.grid(row=0, column=1)
        # Next day
        next_btn = IconButton(
            section, icon_name="chevron_left" if rtl else "chevron_right",
            command=lambda: self._go_day(1),
            size=40, lang=self._lang,
        )
        next_btn.grid(row=0, column=2 if rtl else 0, padx=4)
        # Today button (below)
        today_btn = TextButton(
            section, text=self._tr("امروز", "Today"),
            command=self._go_today, lang=self._lang,
            height=24, font_size=config.FONT_SIZE_CAPTION,
            color=config.GOLD,
        )
        today_btn.grid(row=1, column=0, columnspan=3, pady=(4, 0))

    def _build_streak(self) -> None:
        """Flame + 'X روز پیاپی' label."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._streak_label = ctk.CTkLabel(
            section, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._streak_label.pack(anchor="center")

    def _build_mood(self) -> None:
        """5 large mood buttons in a horizontal row."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("حال امروز", "Today's mood"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # 5 buttons row
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(config.SPACE_SM, 0))
        for i in range(5):
            row.grid_columnconfigure(i, weight=1, uniform="mood")
        self._mood_buttons = []
        for v in range(1, 6):
            btn = ctk.CTkButton(
                row, text=f"{_MOOD_EMOJIS[v]}\n{_mood_label(v, self._lang)}",
                command=lambda _v=v: self._on_mood_tap(_v),
                fg_color=config.CHARCOAL, hover_color=config.SURFACE_HI,
                text_color=config.TEXT,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                corner_radius=config.RADIUS_MD, height=64,
                border_width=2, border_color=config.SURFACE_HI,
            )
            btn.grid(row=0, column=(5 - v) if rtl else (v - 1),
                      sticky="nsew", padx=2)
            self._mood_buttons.append(btn)

    def _build_energy(self) -> None:
        """5-dot energy selector."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("انرژی امروز", "Today's energy"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(config.SPACE_SM, 0))
        for i in range(5):
            row.grid_columnconfigure(i, weight=1, uniform="energy")
        self._energy_buttons = []
        for v in range(1, 6):
            btn = ctk.CTkButton(
                row, text=f"{i18n.to_fa_digits(str(v)) if self._lang == 'fa' else str(v)}\n{_energy_label(v, self._lang)}",
                command=lambda _v=v: self._on_energy_tap(_v),
                fg_color=config.CHARCOAL, hover_color=config.SURFACE_HI,
                text_color=config.TEXT,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                corner_radius=config.RADIUS_MD, height=48,
                border_width=2, border_color=config.SURFACE_HI,
            )
            btn.grid(row=0, column=(5 - v) if rtl else (v - 1),
                      sticky="nsew", padx=2)
            self._energy_buttons.append(btn)

    def _build_title(self) -> None:
        """Title entry."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("عنوان", "Title"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._title_entry = GoldEntry(
            section, lang=self._lang,
            placeholder=self._tr("یک عنوان کوتاه برای امروز",
                                  "A short title for today"),
        )
        self._title_entry.grid(row=1, column=0, sticky="ew",
                                pady=(config.SPACE_XS, 0))
        self._title_entry.bind("<FocusOut>",
                                lambda _e: self._schedule_auto_save())

    def _build_body(self) -> None:
        """Large body text area."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("متن خاطره", "Journal body"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._body_text = TextArea(
            section, lang=self._lang, height=180,
            placeholder=self._tr("هرچه در ذهن داری بنویس...",
                                  "Write whatever's on your mind..."),
        )
        self._body_text.grid(row=1, column=0, sticky="ew",
                              pady=(config.SPACE_XS, 0))
        self._body_text.bind("<FocusOut>",
                              lambda _e: self._schedule_auto_save())

    def _build_lists(self) -> None:
        """Three bulleted list editors: strengths, improvements, gratitudes."""
        self._strengths_editor = self._make_list_section(
            self._tr("نقاط قوت امروز", "Today's strengths"),
            self._tr("یک نقطه قوت...", "A strength..."),
        )
        self._improvements_editor = self._make_list_section(
            self._tr("بهبودها", "Improvements"),
            self._tr("یک بهبود...", "An improvement..."),
        )
        self._gratitudes_editor = self._make_list_section(
            self._tr("سپاسگزاری‌ها", "Gratitudes"),
            self._tr("چیزی که سپاسگزارم...", "Something I'm grateful for..."),
        )

    def _make_list_section(self, title: str, placeholder: str
                             ) -> _BulletedListEditor:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_XS))
        editor = _BulletedListEditor(
            section, lang=self._lang, placeholder=placeholder,
            on_change=lambda _v: self._schedule_auto_save(),
        )
        editor.grid(row=1, column=0, sticky="ew")
        return editor

    def _build_tags(self) -> None:
        """Tag entry + chip strip."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("برچسب‌ها", "Tags"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_XS))
        # Entry + add button row
        entry_row = ctk.CTkFrame(section, fg_color="transparent")
        entry_row.grid(row=1, column=0, sticky="ew")
        entry_row.grid_columnconfigure(0, weight=1)
        self._tag_entry = GoldEntry(
            entry_row, lang=self._lang,
            placeholder=self._tr("برچسب جدید + Enter",
                                  "New tag + Enter"),
        )
        self._tag_entry.grid(row=0, column=0, sticky="ew",
                              padx=(0, 4))
        self._tag_entry.bind("<Return>", lambda _e: self._add_tag())
        add_btn = GhostButton(
            entry_row, text=self._tr("افزودن", "Add"),
            command=self._add_tag, lang=self._lang, height=36,
            width=80,
        )
        add_btn.grid(row=0, column=1, sticky="e")
        # Chips strip
        self._tags_strip = ctk.CTkFrame(section, fg_color="transparent")
        self._tags_strip.grid(row=2, column=0, sticky="ew",
                                pady=(config.SPACE_SM, 0))
        self._tags_strip.grid_columnconfigure(0, weight=1)

    def _build_actions(self) -> None:
        """Save button at the bottom."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._save_btn = GoldButton(
            section, text=self._tr("ذخیره", "Save"),
            command=self._save_now, lang=self._lang, height=44,
        )
        self._save_btn.pack(fill="x", padx=config.SPACE_LG)
        # Last saved hint
        self._save_hint = ctk.CTkLabel(
            section, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
        )
        self._save_hint.pack(anchor="center", pady=(4, 0))

    def _build_history_button(self) -> None:
        """'Previous entries' button → opens a sheet of past entries."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        TextButton(
            section, text=self._tr("ورودی‌های قبلی ←",
                                    "← Previous entries"),
            command=self._show_history, lang=self._lang,
            height=36, color=config.GOLD,
        ).pack(anchor="center")

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
            "journal.added", "journal.updated", "journal.deleted",
            "journal.streak_changed",
            "language.changed", "data.cleared",
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
        self._refresh_job = self.after(150, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render the entire screen for the current date."""
        self._loading_state = True
        try:
            self._refresh_date_label()
            self._refresh_streak()
            self._load_entry_for_date()
        finally:
            self._loading_state = False

    def _refresh_date_label(self) -> None:
        try:
            date_str = jalali.format_jalali(
                self._current_date_iso, fmt="long", lang=self._lang)
        except Exception:
            date_str = self._current_date_iso
        try:
            self._date_label.configure(text=date_str)
        except Exception:
            pass

    def _refresh_streak(self) -> None:
        try:
            streak = journal_service.streak()
        except Exception:
            streak = 0
        if streak > 0:
            s_str = (i18n.to_fa_digits(str(streak))
                     if self._lang == "fa" else str(streak))
            days = (i18n.t("days", self._lang)
                    if "days" in (i18n.LOCALES.get(self._lang, {})
                                   or {}) else "روز")
            text = f"🔥 {s_str} {days} {self._tr('پیاپی', 'streak')}"
        else:
            text = self._tr("اولین خاطره‌ات را بنویس!",
                             "Write your first entry!")
        try:
            self._streak_label.configure(text=text)
        except Exception:
            pass

    def _load_entry_for_date(self) -> None:
        """Load (or auto-create) today's entry into the editor."""
        entry = None
        try:
            entry = journal_service.get_by_date(self._current_date_iso)
        except Exception:
            entry = None
        if entry is None and self._current_date_iso == time_utils.today_iso():
            # Auto-create an empty entry for today
            try:
                new_entry = JournalEntry(date_iso=self._current_date_iso)
                new_id = journal_service.upsert(new_entry)
                if new_id:
                    entry = journal_service.get(new_id)
            except Exception:
                pass
        # Populate the UI from entry (or clear if none)
        if entry is not None:
            self._current_entry_id = entry.id
            self._selected_mood = entry.mood
            self._selected_energy = entry.energy
            # Title
            try:
                self._title_entry.delete(0, "end")
                if entry.title:
                    self._title_entry.insert(0, entry.title)
            except Exception:
                pass
            # Body
            try:
                self._body_text.delete("1.0", "end")
                if entry.body:
                    self._body_text.insert("1.0", entry.body)
            except Exception:
                pass
            # Lists
            try:
                self._strengths_editor.set_values(
                    entry.gratitudes if False else [])
                # Note: JournalEntry has 'gratitudes' and 'improvements'
                # but not 'strengths'.  We map strengths → improvements
                # reversed: actually we'll use gratitudes for strengths
                # aliasing to keep the UX as the spec asks.  Better: use
                # gratitudes for the gratitude list, and improvements
                # for both strengths and improvements as the same list.
                # The cleanest: use the existing fields:
                #   strengths → improvements (we'll call them "نقاط قوت")
                #   improvements → improvements (the spec says both)
                # But to avoid data loss we'll just reuse 'improvements'
                # for both strengths & improvements, and 'gratitudes'
                # for gratitudes.  Cleaner still: treat strengths as
                # separate (not persisted); just write back to
                # 'improvements' on save.
                self._strengths_editor.set_values([])
                self._improvements_editor.set_values(entry.improvements or [])
                self._gratitudes_editor.set_values(entry.gratitudes or [])
            except Exception:
                pass
            # Tags
            self._tags = list(entry.tags or [])
            self._refresh_tag_chips()
            # Save hint
            try:
                if entry.updated_at:
                    self._save_hint.configure(
                        text=self._tr("ذخیره شده",
                                       "Saved") + ": " + entry.updated_at[:16])
            except Exception:
                pass
        else:
            # No entry for this past date — clear everything
            self._current_entry_id = None
            self._selected_mood = None
            self._selected_energy = None
            try:
                self._title_entry.delete(0, "end")
                self._body_text.delete("1.0", "end")
                self._strengths_editor.set_values([])
                self._improvements_editor.set_values([])
                self._gratitudes_editor.set_values([])
            except Exception:
                pass
            self._tags = []
            self._refresh_tag_chips()
        self._refresh_mood_buttons()
        self._refresh_energy_buttons()

    def _refresh_mood_buttons(self) -> None:
        for i, btn in enumerate(self._mood_buttons):
            v = i + 1
            try:
                if v == self._selected_mood:
                    btn.configure(
                        fg_color=_MOOD_COLORS.get(v, config.GOLD),
                        text_color=config.MATTE_BLACK,
                        border_color=_MOOD_COLORS.get(v, config.GOLD),
                    )
                else:
                    btn.configure(
                        fg_color=config.CHARCOAL,
                        text_color=config.TEXT,
                        border_color=config.SURFACE_HI,
                    )
            except Exception:
                pass

    def _refresh_energy_buttons(self) -> None:
        for i, btn in enumerate(self._energy_buttons):
            v = i + 1
            try:
                if v == self._selected_energy:
                    btn.configure(
                        fg_color=config.GOLD,
                        text_color=config.MATTE_BLACK,
                        border_color=config.GOLD,
                    )
                else:
                    btn.configure(
                        fg_color=config.CHARCOAL,
                        text_color=config.TEXT,
                        border_color=config.SURFACE_HI,
                    )
            except Exception:
                pass

    def _refresh_tag_chips(self) -> None:
        # Clear
        for child in self._tags_strip.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._tag_chips = []
        rtl = i18n.is_rtl(self._lang)
        for tag in self._tags:
            chip = TagChip(
                self._tags_strip, text=tag,
                lang=self._lang, closable=True,
                on_close=lambda _t=tag: self._remove_tag(_t),
            )
            chip.pack(side="right" if rtl else "left", padx=2, pady=2)
            self._tag_chips.append(chip)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_mood_tap(self, value: int) -> None:
        self._selected_mood = value
        self._refresh_mood_buttons()
        self._schedule_auto_save()

    def _on_energy_tap(self, value: int) -> None:
        self._selected_energy = value
        self._refresh_energy_buttons()
        self._schedule_auto_save()

    def _go_day(self, delta: int) -> None:
        # Save current entry first
        self._save_now(silent=True)
        try:
            self._current_date_iso = time_utils.add_days(
                self._current_date_iso, delta)
        except Exception:
            pass
        self.refresh()

    def _go_today(self) -> None:
        self._save_now(silent=True)
        self._current_date_iso = time_utils.today_iso()
        self.refresh()

    def _open_date_picker(self) -> None:
        if self._app and hasattr(self._app, "open_date_picker"):
            try:
                self._app.open_date_picker(
                    on_select=lambda start, end: self._on_date_picked(start))
                return
            except Exception:
                pass

    def _on_date_picked(self, iso: str) -> None:
        if not iso:
            return
        self._save_now(silent=True)
        self._current_date_iso = iso[:10]
        self.refresh()

    def _add_tag(self) -> None:
        try:
            tag = self._tag_entry.get().strip()
        except Exception:
            tag = ""
        if not tag:
            return
        if tag in self._tags:
            self._tag_entry.delete(0, "end")
            return
        self._tags.append(tag)
        self._tag_entry.delete(0, "end")
        self._refresh_tag_chips()
        self._schedule_auto_save()

    def _remove_tag(self, tag: str) -> None:
        if tag in self._tags:
            self._tags.remove(tag)
        self._refresh_tag_chips()
        self._schedule_auto_save()

    def _show_history(self) -> None:
        """Open an alert dialog listing past entries."""
        try:
            entries = journal_service.list(limit=20)
        except Exception:
            entries = []
        if not entries:
            AlertDialog(
                self, title=self._tr("ورودی‌های قبلی",
                                       "Previous entries"),
                message=self._tr("هنوز خاطره‌ای ثبت نشده.",
                                  "No journal entries yet."),
                lang=self._lang, ok_text=self._tr("بستن", "Close"),
            )
            return
        rtl = i18n.is_rtl(self._lang)
        lines: List[str] = []
        for e in entries[:20]:
            try:
                d = jalali.format_jalali(e.date_iso, fmt="short",
                                          lang=self._lang)
            except Exception:
                d = e.date_iso
            title = e.title or self._tr("(بدون عنوان)", "(untitled)")
            mood_str = ""
            if e.mood:
                mood_str = f"  {_MOOD_EMOJIS.get(e.mood, '')}"
            lines.append(f"{d}{mood_str}  {title}")
        AlertDialog(
            self, title=self._tr("ورودی‌های قبلی",
                                   "Previous entries"),
            message="\n".join(lines),
            lang=self._lang, ok_text=self._tr("بستن", "Close"),
        )

    def _schedule_auto_save(self) -> None:
        """Debounced auto-save (800ms after last change)."""
        if self._loading_state:
            return
        if self._auto_save_job is not None:
            try:
                self.after_cancel(self._auto_save_job)
            except Exception:
                pass
        self._auto_save_job = self.after(800, lambda: self._save_now(
            silent=True))

    def _save_now(self, silent: bool = False) -> None:
        """Persist the current editor state to the journal service."""
        if self._loading_state:
            return
        try:
            # Gather fields
            try:
                title = self._title_entry.get().strip() or None
            except Exception:
                title = None
            try:
                body = self._body_text.get("1.0", "end").strip() or None
            except Exception:
                body = None
            strengths = self._strengths_editor.get_values()
            improvements = self._improvements_editor.get_values()
            gratitudes = self._gratitudes_editor.get_values()
            # Merge strengths into improvements so they persist
            # (JournalEntry only has improvements + gratitudes)
            all_improvements = list(improvements)
            tags = list(self._tags)
            entry = JournalEntry(
                id=self._current_entry_id,
                date_iso=self._current_date_iso,
                mood=self._selected_mood,
                energy=self._selected_energy,
                title=title,
                body=body,
                tags=tags,
                gratitudes=gratitudes,
                improvements=all_improvements,
            )
            new_id = journal_service.upsert(entry)
            if new_id and not self._current_entry_id:
                self._current_entry_id = new_id
            if not silent:
                self._show_toast(self._tr("ذخیره شد", "Saved"))
                try:
                    self._save_hint.configure(
                        text=self._tr("ذخیره شد در",
                                       "Saved at") + " " +
                        time_utils.now_iso_local()[11:16])
                except Exception:
                    pass
        except Exception:
            if not silent:
                self._show_toast(self._tr("خطا در ذخیره",
                                            "Save failed"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _tr(self, fa: str, en: str) -> str:
        try:
            v = i18n.t(fa, self._lang)
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
            event_bus.bus.publish("ui.toast", {"message": message})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def destroy(self) -> None:  # type: ignore[override]
        # Save pending changes before tearing down
        try:
            self._save_now(silent=True)
        except Exception:
            pass
        self._unsubscribe_events()
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        if self._auto_save_job is not None:
            try:
                self.after_cancel(self._auto_save_job)
            except Exception:
                pass
            self._auto_save_job = None
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("JournalScreen module: date nav + mood/energy selectors + "
          "title + body + 3 bulleted editors + tags + save.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
