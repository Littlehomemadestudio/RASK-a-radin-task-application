"""
rask.ui.screens.mood_screen
===========================

Mood tracker screen — standalone mood/energy logging with trend charts.

Mirrors the *Mood* view from the web app.  Uses
:class:`rask.features.mood_tracker.MoodService` as the source of truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"حال و انرژی"``
    2. **Today's mood selector** — 5 large buttons (1..5) with emoji +
       Persian label
    3. **Today's energy selector** — 5-dot selector (1..5)
    4. **Today's notes** — single-line entry for a short note
    5. **Today's triggers** — multi-select chips (work, sleep, exercise,
       food, social, weather, etc.)
    6. **Save button** — explicit save (auto-saves too)
    7. **Mood trend chart** — last 30 days line chart
    8. **Energy trend chart** — last 30 days line chart
    9. **Mood distribution** — donut chart of the last 30 days
    10. **Mood-activity correlation card** — ``"وقتی ورزش می‌کنی، حالت بهتره"``
    11. **Weekly mood heatmap** — 7-day × mood-level grid

Auto-refresh
------------
Subscribes to ``mood.added`` / ``mood.updated`` / ``mood.deleted`` /
``language.changed`` / ``data.cleared`` / ``activity.added`` /
``activity.updated`` (for correlation recalc).
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
from ...core import event_bus, time_utils
from ...features.mood_tracker import mood_service
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.badges import Chip
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.inputs import GoldEntry
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.charts import LineChart, DonutChart, BarChart

__all__ = ["MoodScreen"]


# =============================================================================
# === Constants                                                              ===
# =============================================================================

_MOOD_EMOJIS: Dict[int, str] = {
    1: "😞", 2: "😕", 3: "😐", 4: "🙂", 5: "😄",
}
_MOOD_LABELS_FA: Dict[int, str] = {
    1: "خیلی بد", 2: "بد", 3: "معمولی", 4: "خوب", 5: "عالی",
}
_MOOD_LABELS_EN: Dict[int, str] = {
    1: "Very Bad", 2: "Bad", 3: "Neutral", 4: "Good", 5: "Great",
}
_ENERGY_LABELS_FA: Dict[int, str] = {
    1: "خسته", 2: "کم‌انرژی", 3: "متوسط", 4: "پرانرژی", 5: "پرقدرت",
}
_ENERGY_LABELS_EN: Dict[int, str] = {
    1: "Exhausted", 2: "Low", 3: "Medium", 4: "Energetic", 5: "Powerful",
}
_MOOD_COLORS: Dict[int, str] = {
    1: config.DANGER, 2: config.WARNING, 3: config.TEXT_DIM,
    4: config.GOLD, 5: config.SUCCESS,
}
_MOOD_DIST_COLORS: List[str] = [
    config.DANGER, config.WARNING, config.TEXT_DIM,
    config.GOLD, config.SUCCESS,
]
_TRIGGERS_FA: List[str] = [
    "کار", "خواب", "ورزش", "غذا", "اجتماعی", "هوا",
    "خانواده", "مالی", "سلامتی", "حمل‌ونقل",
]
_TRIGGERS_EN: List[str] = [
    "work", "sleep", "exercise", "food", "social", "weather",
    "family", "finance", "health", "transit",
]


def _mood_label(v: int, lang: str) -> str:
    if lang == "fa":
        return _MOOD_LABELS_FA.get(v, str(v))
    return _MOOD_LABELS_EN.get(v, str(v))


def _energy_label(v: int, lang: str) -> str:
    if lang == "fa":
        return _ENERGY_LABELS_FA.get(v, str(v))
    return _ENERGY_LABELS_EN.get(v, str(v))


def _trigger_list(lang: str) -> List[str]:
    return _TRIGGERS_FA if lang == "fa" else _TRIGGERS_EN


# =============================================================================
# === MoodScreen                                                             ===
# =============================================================================

class MoodScreen(ctk.CTkFrame):
    """Mood tracker screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
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
        self._refresh_job: Optional[Any] = None
        self._refresh_pending: bool = False
        self._today_iso: str = time_utils.today_iso()
        self._today_entry_id: Optional[int] = None
        self._selected_mood: Optional[int] = None
        self._selected_energy: Optional[int] = None
        self._selected_triggers: List[str] = []
        self._mood_buttons: List[ctk.CTkButton] = []
        self._energy_buttons: List[ctk.CTkButton] = []
        self._trigger_chips: List[ctk.CTkBaseClass] = []
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
        self._header = Header(
            self, title=self._tr("حال و انرژی", "Mood & Energy"),
            lang=self._lang, height=56,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_today_mood()
        self._build_today_energy()
        self._build_today_notes()
        self._build_triggers()
        self._build_save()
        self._build_mood_trend()
        self._build_energy_trend()
        self._build_mood_distribution()
        self._build_correlation()
        self._build_heatmap()

    def _build_today_mood(self) -> None:
        """5 large mood buttons."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("حال امروز", "Today's mood"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
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
                corner_radius=config.RADIUS_MD, height=72,
                border_width=2, border_color=config.SURFACE_HI,
            )
            btn.grid(row=0, column=(5 - v) if rtl else (v - 1),
                      sticky="nsew", padx=2)
            self._mood_buttons.append(btn)

    def _build_today_energy(self) -> None:
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
            label_v = (i18n.to_fa_digits(str(v))
                       if self._lang == "fa" else str(v))
            btn = ctk.CTkButton(
                row, text=f"{label_v}\n{_energy_label(v, self._lang)}",
                command=lambda _v=v: self._on_energy_tap(_v),
                fg_color=config.CHARCOAL, hover_color=config.SURFACE_HI,
                text_color=config.TEXT,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                corner_radius=config.RADIUS_MD, height=56,
                border_width=2, border_color=config.SURFACE_HI,
            )
            btn.grid(row=0, column=(5 - v) if rtl else (v - 1),
                      sticky="nsew", padx=2)
            self._energy_buttons.append(btn)

    def _build_today_notes(self) -> None:
        """Single-line notes entry."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("یادداشت", "Notes"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._notes_entry = GoldEntry(
            section, lang=self._lang,
            placeholder=self._tr("یادداشت کوتاه درباره حال امروز...",
                                  "Short note about today's mood..."),
        )
        self._notes_entry.grid(row=1, column=0, sticky="ew",
                                pady=(config.SPACE_XS, 0))
        self._notes_entry.bind("<FocusOut>",
                                lambda _e: self._schedule_auto_save())

    def _build_triggers(self) -> None:
        """Multi-select trigger chips."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("عوامل تاثیرگذار", "Triggers"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._triggers_strip = ctk.CTkFrame(section, fg_color="transparent")
        self._triggers_strip.grid(row=1, column=0, sticky="ew",
                                    pady=(config.SPACE_XS, 0))
        self._triggers_strip.grid_columnconfigure(0, weight=1)
        # Build chips
        self._trigger_chips = []
        for trig in _trigger_list(self._lang):
            chip = PillButton(
                self._triggers_strip, text=trig,
                command=lambda _t=trig: self._on_trigger_tap(_t),
                lang=self._lang, height=32,
                color=config.CHARCOAL,
                text_color=config.TEXT,
                font_size=config.FONT_SIZE_SMALL,
            )
            chip.pack(side="right" if rtl else "left", padx=2, pady=2)
            self._trigger_chips.append(chip)

    def _build_save(self) -> None:
        """Save button + auto-save hint."""
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
        self._save_hint = ctk.CTkLabel(
            section, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
        )
        self._save_hint.pack(anchor="center", pady=(4, 0))

    def _build_mood_trend(self) -> None:
        """30-day mood trend line chart."""
        self._mood_trend_card = self._make_chart_card(
            self._next_row(),
            self._tr("روند حال (۳۰ روز)", "Mood trend (30 days)"),
        )
        self._mood_trend_chart = LineChart(
            self._mood_trend_card.content,
            data=[], width=460, height=160, lang=self._lang,
        )
        self._mood_trend_chart.grid(row=1, column=0, sticky="ew",
                                      padx=4, pady=4)

    def _build_energy_trend(self) -> None:
        """30-day energy trend line chart."""
        self._energy_trend_card = self._make_chart_card(
            self._next_row(),
            self._tr("روند انرژی (۳۰ روز)", "Energy trend (30 days)"),
        )
        self._energy_trend_chart = LineChart(
            self._energy_trend_card.content,
            data=[], width=460, height=160, lang=self._lang,
        )
        self._energy_trend_chart.grid(row=1, column=0, sticky="ew",
                                        padx=4, pady=4)

    def _build_mood_distribution(self) -> None:
        """Donut chart of mood distribution."""
        self._dist_card = self._make_chart_card(
            self._next_row(),
            self._tr("توزیع حال", "Mood distribution"),
        )
        self._dist_chart = DonutChart(
            self._dist_card.content,
            data=[], width=200, height=200,
            center_label=self._tr("۳۰ روز", "30 days"),
            lang=self._lang,
        )
        self._dist_chart.grid(row=1, column=0, padx=4, pady=4)

    def _build_correlation(self) -> None:
        """Mood-activity correlation card."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_SM, 0))
        section.grid_columnconfigure(0, weight=1)
        self._correlation_card = Card(section, lang=self._lang,
                                        padding=config.SPACE_LG)
        self._correlation_card.grid(row=0, column=0, sticky="ew")
        self._correlation_card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            self._correlation_card.content,
            text=self._tr("همبستگی حال و فعالیت",
                            "Mood-Activity Correlation"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._correlation_body = ctk.CTkFrame(
            self._correlation_card.content, fg_color="transparent")
        self._correlation_body.grid(row=1, column=0, sticky="ew",
                                      pady=(config.SPACE_SM, 0))
        self._correlation_body.grid_columnconfigure(0, weight=1)

    def _build_heatmap(self) -> None:
        """7-day mood heatmap (day × mood-level grid)."""
        self._heatmap_card = self._make_chart_card(
            self._next_row(),
            self._tr("نقشه حرارتی هفتگی", "Weekly mood heatmap"),
        )
        # Build the 7x5 grid manually using small frames
        self._heatmap_grid = ctk.CTkFrame(
            self._heatmap_card.content, fg_color="transparent")
        self._heatmap_grid.grid(row=1, column=0, sticky="ew",
                                  padx=4, pady=4)
        self._heatmap_grid.grid_columnconfigure(0, weight=1)
        for i in range(1, 8):
            self._heatmap_grid.grid_columnconfigure(i, weight=0,
                                                     uniform="hm")

    def _make_chart_card(self, row: int, title: str) -> Card:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=row, column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_SM, 0))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card.content, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        return card

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
            "mood.added", "mood.updated", "mood.deleted",
            "language.changed", "data.cleared",
            "activity.added", "activity.updated",
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
        """Re-render everything."""
        self._today_iso = time_utils.today_iso()
        self._loading_state = True
        try:
            self._load_today_entry()
            self._refresh_mood_buttons()
            self._refresh_energy_buttons()
            self._refresh_trigger_chips()
            self._refresh_mood_trend()
            self._refresh_energy_trend()
            self._refresh_distribution()
            self._refresh_correlation()
            self._refresh_heatmap()
        finally:
            self._loading_state = False

    def _load_today_entry(self) -> None:
        """Load today's mood entry (if any) into the UI."""
        entry = None
        try:
            entries = mood_service.get_by_date(self._today_iso)
            if entries:
                entry = entries[-1]  # most recent today
        except Exception:
            entry = None
        if entry is not None:
            self._today_entry_id = entry.id
            self._selected_mood = entry.mood
            self._selected_energy = entry.energy
            try:
                self._notes_entry.delete(0, "end")
                if entry.notes:
                    self._notes_entry.insert(0, entry.notes)
            except Exception:
                pass
            self._selected_triggers = list(entry.triggers or [])
            try:
                if entry.id:
                    self._save_hint.configure(
                        text=self._tr("ذخیره شده", "Saved"))
            except Exception:
                pass
        else:
            self._today_entry_id = None
            self._selected_mood = None
            self._selected_energy = None
            try:
                self._notes_entry.delete(0, "end")
            except Exception:
                pass
            self._selected_triggers = []

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

    def _refresh_trigger_chips(self) -> None:
        for i, chip in enumerate(self._trigger_chips):
            trig = _trigger_list(self._lang)[i]
            selected = trig in self._selected_triggers
            try:
                chip.configure(
                    fg_color=(config.GOLD if selected
                                else config.CHARCOAL),
                    text_color=(config.MATTE_BLACK if selected
                                  else config.TEXT),
                )
            except Exception:
                pass

    def _refresh_mood_trend(self) -> None:
        try:
            trend = mood_service.trend(days=30)
            values = [float(t.get("mood_avg") or 0.0) for t in trend]
            self._mood_trend_chart.set_data([{
                "label": self._tr("حال", "Mood"),
                "values": values,
                "color": config.GOLD,
            }])
        except Exception:
            pass

    def _refresh_energy_trend(self) -> None:
        try:
            trend = mood_service.trend(days=30)
            values = [float(t.get("energy_avg") or 0.0) for t in trend]
            self._energy_trend_chart.set_data([{
                "label": self._tr("انرژی", "Energy"),
                "values": values,
                "color": config.INFO,
            }])
        except Exception:
            pass

    def _refresh_distribution(self) -> None:
        try:
            dist = mood_service.mood_distribution(days=30)
            data = [
                {"label": _mood_label(v, self._lang),
                 "value": dist.get(v, 0),
                 "color": _MOOD_DIST_COLORS[v - 1]}
                for v in range(1, 6)
                if dist.get(v, 0) > 0
            ]
            self._dist_chart.set_data(data)
        except Exception:
            pass

    def _refresh_correlation(self) -> None:
        """Render the mood-activity correlation card."""
        # Clear old children
        for child in self._correlation_body.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        try:
            corr = mood_service.correlation_with_activities()
        except Exception:
            corr = {}
        by_cat = corr.get("by_category", []) if corr else []
        overall = corr.get("overall_avg", 0.0) if corr else 0.0
        if not by_cat:
            ctk.CTkLabel(
                self._correlation_body,
                text=self._tr("داده کافی نیست",
                                "Not enough data yet"),
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).grid(row=0, column=0, sticky="ew")
            return
        rtl = i18n.is_rtl(self._lang)
        # Sort by delta descending — show top correlations
        sorted_cats = sorted(by_cat,
                              key=lambda c: abs(c.get("delta", 0.0)),
                              reverse=True)[:3]
        for i, c in enumerate(sorted_cats):
            name = c.get("category_name", "—")
            color = c.get("category_color") or config.GOLD
            delta = float(c.get("delta", 0.0) or 0.0)
            sample = int(c.get("sample_size", 0) or 0)
            if delta > 0.2:
                arrow = "↑"
                msg = self._tr(
                    f"وقتی {name} می‌کنی، حالت بهتره",
                    f"Doing {name} improves your mood")
                msg_color = config.SUCCESS
            elif delta < -0.2:
                arrow = "↓"
                msg = self._tr(
                    f"وقتی {name} می‌کنی، حالت بدتره",
                    f"Doing {name} lowers your mood")
                msg_color = config.DANGER
            else:
                arrow = "—"
                msg = self._tr(
                    f"{name} تاثیر قابل توجهی روی حالت ندارد",
                    f"{name} doesn't significantly affect your mood")
                msg_color = config.TEXT_DIM
            # Card row
            row_frame = ctk.CTkFrame(
                self._correlation_body, fg_color="transparent")
            row_frame.grid(row=i, column=0, sticky="ew",
                            pady=(0 if i == 0 else 4, 4))
            row_frame.grid_columnconfigure(1, weight=1)
            # Color dot
            dot = ctk.CTkFrame(row_frame, width=10, height=10,
                                 fg_color=color,
                                 corner_radius=config.RADIUS_PILL)
            dot.grid(row=0, column=1 if rtl else 0,
                      padx=(0 if rtl else 0, 4 if rtl else 4),
                      pady=8, sticky="n")
            # Arrow
            ctk.CTkLabel(
                row_frame, text=arrow,
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                        weight="bold", lang=self._lang),
                text_color=msg_color,
            ).grid(row=0, column=0 if rtl else 1, padx=4)
            # Message
            ctk.CTkLabel(
                row_frame, text=msg,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
                wraplength=320, justify="right" if rtl else "left",
            ).grid(row=0, column=2 if rtl else 1, sticky="e" if rtl
                    else "w", padx=4)

    def _refresh_heatmap(self) -> None:
        """Build a 7-day × mood-level grid showing mood counts."""
        # Clear grid children
        for child in self._heatmap_grid.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        try:
            from ...core.time_utils import range_days
            start = time_utils.add_days(self._today_iso, -6)
            dates = list(range_days(start, self._today_iso))
        except Exception:
            dates = []
        if not dates:
            return
        rtl = i18n.is_rtl(self._lang)
        # Header row: empty + weekday abbreviations
        ctk.CTkLabel(
            self._heatmap_grid, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
        ).grid(row=0, column=0, padx=2)
        for i, d in enumerate(dates):
            col = (7 - i) if rtl else (i + 1)
            # Weekday short
            from datetime import date as _date
            try:
                py_wd = _date.fromisoformat(d[:10]).weekday()
                sat_first = (py_wd + 2) % 7
                if self._lang == "fa":
                    label = ["ش", "ی", "د", "س", "چ", "پ", "ج"][sat_first]
                else:
                    label = ["Sa", "Su", "Mo", "Tu", "We", "Th",
                              "Fr"][sat_first]
            except Exception:
                label = "—"
            ctk.CTkLabel(
                self._heatmap_grid, text=label,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).grid(row=0, column=col, padx=2)
        # Build per-day mood counts
        for v in range(5, 0, -1):  # 5..1 top-to-bottom
            row_idx = 5 - v + 1
            # Row label (emoji)
            ctk.CTkLabel(
                self._heatmap_grid, text=_MOOD_EMOJIS[v],
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang="en"),
                text_color=config.TEXT,
            ).grid(row=row_idx, column=0, padx=2)
            for i, d in enumerate(dates):
                col = (7 - i) if rtl else (i + 1)
                # Count entries for this day with this mood
                count = 0
                try:
                    entries = mood_service.get_by_date(d)
                    count = sum(1 for e in entries
                                  if int(e.mood) == v)
                except Exception:
                    count = 0
                if count > 0:
                    bg = _MOOD_COLORS.get(v, config.GOLD)
                    fg = config.MATTE_BLACK
                    txt = (i18n.to_fa_digits(str(count))
                            if self._lang == "fa" else str(count))
                else:
                    bg = config.SURFACE
                    fg = config.TEXT_FAINT
                    txt = ""
                cell = ctk.CTkFrame(
                    self._heatmap_grid, width=32, height=32,
                    fg_color=bg, corner_radius=config.RADIUS_SM,
                )
                cell.grid(row=row_idx, column=col, padx=2, pady=2)
                cell.grid_propagate(False)
                ctk.CTkLabel(
                    cell, text=txt,
                    font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                            weight="bold", lang=self._lang),
                    text_color=fg,
                ).pack(expand=True, fill="both")

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

    def _on_trigger_tap(self, trigger: str) -> None:
        if trigger in self._selected_triggers:
            self._selected_triggers.remove(trigger)
        else:
            self._selected_triggers.append(trigger)
        self._refresh_trigger_chips()
        self._schedule_auto_save()

    def _schedule_auto_save(self) -> None:
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
        if self._loading_state:
            return
        if self._selected_mood is None:
            if not silent:
                self._show_toast(self._tr("اول حال امروز را انتخاب کن",
                                            "Pick today's mood first"))
            return
        try:
            notes = self._notes_entry.get().strip() or None
        except Exception:
            notes = None
        try:
            if self._today_entry_id is not None:
                mood_service.update(
                    self._today_entry_id,
                    mood=int(self._selected_mood),
                    energy=self._selected_energy,
                    notes=notes,
                    triggers=list(self._selected_triggers),
                )
            else:
                new_id = mood_service.add(
                    date_iso=self._today_iso,
                    mood=int(self._selected_mood),
                    energy=self._selected_energy,
                    notes=notes,
                    triggers=list(self._selected_triggers),
                )
                if new_id:
                    self._today_entry_id = new_id
            if not silent:
                self._show_toast(self._tr("ذخیره شد", "Saved"))
                try:
                    self._save_hint.configure(
                        text=self._tr("ذخیره شد در", "Saved at") + " " +
                        time_utils.now_iso_local()[11:16])
                except Exception:
                    pass
            self._schedule_refresh()
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
    print("MoodScreen module: today mood/energy/triggers + 30-day "
          "trends + distribution + correlation + 7-day heatmap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
