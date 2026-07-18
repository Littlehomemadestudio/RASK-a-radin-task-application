"""
rask.ui.screens.achievements_screen
===================================

Extended achievements screen — XP/level display + tier-filtered grid
of achievement cards.

Mirrors the *Achievements* view from the web app.  Uses
:class:`rask.features.achievements_system.AchievementService` as the
source of truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"دستاوردها"`` with XP / level display
    2. **Level progress card** — big level number + level title +
       progress bar (e.g. ``"سطح ۵ • ۲۳۴۰/۳۰۰۰ XP"``)
    3. **Overall summary** — X / Y earned + completion %
    4. **Tier filter** — All / Bronze / Silver / Gold / Platinum segmented
    5. **Achievements grid** — 4-column grid of achievement cards:
       • Earned: full color + earned date + sparkle
       • In progress: progress bar
       • Locked: grayscale
    6. **Confetti animation** — when a new achievement is earned
       (subscribes to ``achievement.earned``)
    7. **Tap for details** — opens a dialog with description + progress

Achievement categories: streaks, time, categories, goals, sessions,
consistency.

Auto-refresh
------------
Subscribes to ``achievement.earned`` / ``achievement.progress_changed``
/ ``activity.added`` / ``activity.updated`` / ``activity.deleted`` /
``streak.incremented`` / ``streak.reset`` / ``goal.added`` /
``goal.updated`` / ``goal.deleted`` / ``language.changed`` /
``data.cleared``.
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
from ...core import event_bus, jalali
from ...features.achievements_system import (
    achievement_service, Achievement,
    TIER_BRONZE, TIER_SILVER, TIER_GOLD, TIER_PLATINUM, TIER_DIAMOND,
    XP_PER_LEVEL, LEVEL_TITLES,
)
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.badges import TierBadge, TIER_COLORS
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.toggles import SegmentedControl
from ..widgets.progress_ring import ProgressRing
from ..widgets.sliders import ProgressBar
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.confetti import Confetti
from ..widgets.dialogs import AlertDialog

__all__ = ["AchievementsScreen"]


# =============================================================================
# === Tier labels                                                            ===
# =============================================================================

_TIER_LABELS_FA: Dict[str, str] = {
    TIER_BRONZE: "برنز",
    TIER_SILVER: "نقره",
    TIER_GOLD: "طلایی",
    TIER_PLATINUM: "پلاتین",
    TIER_DIAMOND: "الماس",
}
_TIER_LABELS_EN: Dict[str, str] = {
    TIER_BRONZE: "Bronze",
    TIER_SILVER: "Silver",
    TIER_GOLD: "Gold",
    TIER_PLATINUM: "Platinum",
    TIER_DIAMOND: "Diamond",
}


def _tier_label(tier: str, lang: str) -> str:
    if lang == "fa":
        return _TIER_LABELS_FA.get(tier, tier)
    return _TIER_LABELS_EN.get(tier, tier)


# =============================================================================
# === Achievement card cell                                                  ===
# =============================================================================

class _AchievementCell(Card):
    """One achievement in the grid."""

    def __init__(
        self,
        master: Any,
        achievement: Achievement,
        lang: str = "fa",
        on_click: Optional[Callable[[Achievement], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("padding", config.SPACE_SM)
        super().__init__(
            master, lang=lang,
            on_click=(on_click and (lambda: on_click(achievement))),
            **kwargs,
        )
        self._achievement = achievement
        self._lang = lang
        earned = achievement.earned_at is not None
        # Layout: icon (top), name (middle), tier / status (bottom)
        self.content.grid_columnconfigure(0, weight=1)
        # Icon container
        icon_frame = ctk.CTkFrame(self.content, fg_color="transparent",
                                    height=64)
        icon_frame.grid(row=0, column=0, pady=(0, 4))
        icon_frame.grid_columnconfigure(0, weight=1)
        # Use TierBadge for the icon
        tier_badge = TierBadge(
            icon_frame, tier=achievement.tier,
            icon_name=achievement.icon or "trophy",
            size=52, earned=earned, lang=lang,
        )
        tier_badge.grid(row=0, column=0)
        # Earned sparkle (overlay)
        if earned:
            sparkle = ctk.CTkLabel(
                icon_frame, text="✨",
                font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                        weight="normal", lang="en"),
                text_color=config.GOLD,
            )
            sparkle.place(relx=0.85, rely=0.15, anchor="center")
        # Locked overlay
        if not earned:
            lock_label = ctk.CTkLabel(
                icon_frame, text="🔒",
                font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                        weight="normal", lang="en"),
                text_color=config.TEXT_DIM,
            )
            lock_label.place(relx=0.5, rely=0.5, anchor="center")
        # Name (truncated)
        name = (achievement.title_fa if lang == "fa"
                 else achievement.title_en) or "—"
        ctk.CTkLabel(
            self.content, text=name,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=lang),
            text_color=config.TEXT if earned else config.TEXT_DIM,
            wraplength=80, justify="center", anchor="center",
        ).grid(row=1, column=0, pady=(2, 0))
        # Tier label
        ctk.CTkLabel(
            self.content, text=_tier_label(achievement.tier, lang),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=lang),
            text_color=(TIER_COLORS.get(achievement.tier, config.GOLD)
                         if earned else config.TEXT_FAINT),
        ).grid(row=2, column=0, pady=(1, 0))
        # Status row: earned date OR progress %
        if earned:
            earned_at = achievement.earned_at or ""
            if earned_at:
                try:
                    date_str = jalali.format_jalali(
                        earned_at[:10], fmt="short", lang=lang)
                except Exception:
                    date_str = earned_at[:10]
            else:
                date_str = "✓"
            ctk.CTkLabel(
                self.content, text=date_str,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=lang),
                text_color=config.GOLD,
            ).grid(row=3, column=0, pady=(1, 0))
        else:
            # Progress bar (small)
            pct = max(0.0, min(1.0, achievement.progress))
            pct_int = int(pct * 100)
            pct_str = (i18n.to_fa_digits(str(pct_int)) + "٪"
                       if lang == "fa" else f"{pct_int}%")
            bar = ProgressBar(self.content, value=pct, animated=False,
                               height=4, width=70)
            bar.grid(row=3, column=0, pady=(2, 0))
            ctk.CTkLabel(
                self.content, text=pct_str,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=lang),
                text_color=config.TEXT_DIM,
            ).grid(row=4, column=0, pady=(1, 0))


# =============================================================================
# === AchievementsScreen                                                     ===
# =============================================================================

class AchievementsScreen(ctk.CTkFrame):
    """Extended achievements screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``trigger_confetti()``
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
        self._achievement_cells: List[_AchievementCell] = []
        self._known_earned_keys: set = set()
        self._tier_filter: str = "all"
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
            self, title=self._tr("دستاوردها", "Achievements"),
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
        self._section_row = 0
        self._build_level_card()
        self._build_summary_card()
        self._build_tier_filter()
        self._build_grid()

    def _build_level_card(self) -> None:
        """Big level + progress card."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Big level number (left/right)
        self._level_label = ctk.CTkLabel(
            card.content, text="—",
            font=_theme.theme.font(size=config.FONT_SIZE_DISPLAY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._level_label.grid(row=0, column=0 if rtl else 1,
                                 rowspan=2, padx=8)
        # Level title + XP bar
        info = ctk.CTkFrame(card.content, fg_color="transparent")
        info.grid(row=0, column=1 if rtl else 0, sticky="ew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        self._level_title_label = ctk.CTkLabel(
            info, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._level_title_label.grid(row=0, column=0, sticky="e" if rtl
                                       else "w")
        self._xp_label = ctk.CTkLabel(
            info, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        )
        self._xp_label.grid(row=1, column=0, sticky="e" if rtl else "w",
                              pady=(2, 0))
        # Progress bar
        self._level_progress = ProgressBar(
            info, value=0.0, animated=True, height=8,
        )
        self._level_progress.grid(row=2, column=0, sticky="ew",
                                    pady=(config.SPACE_SM, 0))

    def _build_summary_card(self) -> None:
        """X / Y earned + completion % card."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        # 3 stat cards
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        for i in range(3):
            row.grid_columnconfigure(i, weight=1, uniform="ach")
        self._earned_card = StatCard(
            row, label=self._tr("کسب شده", "Earned"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._earned_card.grid(row=0, column=0, sticky="nsew",
                                 padx=(0, 4))
        self._locked_card = StatCard(
            row, label=self._tr("قفل‌شده", "Locked"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._locked_card.grid(row=0, column=1, sticky="nsew",
                                 padx=4)
        self._completion_card = StatCard(
            row, label=self._tr("درصد تکمیل", "Completion"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._completion_card.grid(row=0, column=2, sticky="nsew",
                                     padx=(4, 0))

    def _build_tier_filter(self) -> None:
        """Tier segmented control."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        # Filter chips row (custom, since SegmentedControl would
        # require uniform values)
        chips_row = ctk.CTkFrame(section, fg_color="transparent")
        chips_row.pack(anchor="center")
        rtl = i18n.is_rtl(self._lang)
        tiers = ["all", TIER_BRONZE, TIER_SILVER, TIER_GOLD,
                  TIER_PLATINUM, TIER_DIAMOND]
        labels = {t: (self._tr("همه", "All") if t == "all"
                       else _tier_label(t, self._lang))
                  for t in tiers}
        self._tier_chips: Dict[str, ctk.CTkButton] = {}
        for t in tiers:
            chip = ctk.CTkButton(
                chips_row, text=labels[t],
                command=lambda _t=t: self._on_tier_filter(_t),
                fg_color=(config.GOLD if t == self._tier_filter
                            else config.CHARCOAL),
                hover_color=config.GOLD_BRIGHT,
                text_color=(config.MATTE_BLACK if t == self._tier_filter
                              else config.TEXT),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                corner_radius=config.RADIUS_PILL, height=32,
                border_width=2,
                border_color=(config.GOLD if t == self._tier_filter
                                else config.SURFACE_HI),
            )
            chip.pack(side="right" if rtl else "left", padx=4, pady=4)
            self._tier_chips[t] = chip

    def _build_grid(self) -> None:
        """The 4-column achievements grid."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("همه دستاوردها", "All achievements"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        self._grid_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._grid_frame.grid(row=1, column=0, sticky="ew")
        for i in range(4):
            self._grid_frame.grid_columnconfigure(i, weight=1,
                                                    uniform="ach")

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
            "achievement.earned", "achievement.progress_changed",
            "activity.added", "activity.updated", "activity.deleted",
            "streak.incremented", "streak.reset",
            "goal.added", "goal.updated", "goal.deleted",
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
        # Detect newly-earned achievements for confetti
        try:
            ev_name = kwargs.get("event") or ""
            if "achievement.earned" in str(ev_name):
                self._fire_confetti()
        except Exception:
            pass
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
        """Re-render the entire screen."""
        # Fetch all achievements
        try:
            achievements = achievement_service.all()
        except Exception:
            achievements = []
        # Detect newly-earned
        earned_keys = {a.key for a in achievements if a.earned_at}
        if self._achievement_cells and earned_keys - self._known_earned_keys:
            self._fire_confetti()
        self._known_earned_keys = earned_keys
        # Stats
        try:
            stats = achievement_service.stats()
        except Exception:
            stats = {}
        # Update level card
        try:
            level = int(stats.get("level", 1))
            level_str = (i18n.to_fa_digits(str(level))
                          if self._lang == "fa" else str(level))
            self._level_label.configure(text=level_str)
            # Title — e.g. "سطح ۵ • استاد"
            level_title = (stats.get("level_title", "")
                            if self._lang == "fa"
                            else stats.get("level_title_en", ""))
            self._level_title_label.configure(text=level_title)
            # XP — e.g. "۲۳۴۰ / ۳۰۰۰ XP"
            xp_total = int(stats.get("xp_total", 0))
            xp_to_next = int(stats.get("xp_to_next_level", XP_PER_LEVEL))
            xp_in_level = XP_PER_LEVEL - xp_to_next
            xp_str = (f"{i18n.to_fa_digits(str(xp_in_level)) if self._lang == 'fa' else str(xp_in_level)} "
                       f"/ "
                       f"{i18n.to_fa_digits(str(XP_PER_LEVEL)) if self._lang == 'fa' else str(XP_PER_LEVEL)} "
                       f"XP")
            self._xp_label.configure(text=xp_str)
            # Progress bar
            progress = float(stats.get("level_progress", 0.0))
            try:
                self._level_progress.set(progress)
            except Exception:
                pass
        except Exception:
            pass
        # Summary
        try:
            earned_count = int(stats.get("earned_count", 0))
            locked_count = int(stats.get("locked_count", 0))
            total = earned_count + locked_count
            pct = (earned_count / total * 100) if total > 0 else 0.0
            ec_str = (i18n.to_fa_digits(str(earned_count))
                       if self._lang == "fa" else str(earned_count))
            lc_str = (i18n.to_fa_digits(str(locked_count))
                       if self._lang == "fa" else str(locked_count))
            pct_str = (i18n.to_fa_digits(str(int(pct))) + "٪"
                        if self._lang == "fa" else f"{int(pct)}%")
            self._earned_card.set_value(ec_str)
            self._locked_card.set_value(lc_str)
            self._completion_card.set_value(pct_str)
        except Exception:
            pass
        # Filter achievements by tier
        if self._tier_filter == "all":
            filtered = achievements
        else:
            filtered = [a for a in achievements
                         if a.tier == self._tier_filter]
        # Clear old cells
        for child in self._grid_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._achievement_cells = []
        # Build grid (4 columns)
        for i, a in enumerate(filtered):
            row = i // 4
            col = (3 - (i % 4)) if i18n.is_rtl(self._lang) else (i % 4)
            cell = _AchievementCell(
                self._grid_frame, achievement=a,
                lang=self._lang, on_click=self._on_achievement_tap,
            )
            cell.grid(row=row, column=col, sticky="nsew",
                       padx=4, pady=4)
            self._achievement_cells.append(cell)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_tier_filter(self, tier: str) -> None:
        self._tier_filter = tier
        # Update chip highlights
        for t, chip in self._tier_chips.items():
            try:
                chip.configure(
                    fg_color=(config.GOLD if t == tier
                                else config.CHARCOAL),
                    text_color=(config.MATTE_BLACK if t == tier
                                  else config.TEXT),
                    border_color=(config.GOLD if t == tier
                                    else config.SURFACE_HI),
                )
            except Exception:
                pass
        self.refresh()

    def _on_achievement_tap(self, achievement: Achievement) -> None:
        """Show achievement details."""
        name = (achievement.title_fa if self._lang == "fa"
                 else achievement.title_en) or "—"
        desc = (achievement.description_fa if self._lang == "fa"
                 else achievement.description_en) or ""
        tier_label = _tier_label(achievement.tier, self._lang)
        xp_str = (i18n.to_fa_digits(str(achievement.xp_reward))
                  if self._lang == "fa" else str(achievement.xp_reward))
        if achievement.earned_at:
            try:
                date_str = jalali.format_jalali(
                    achievement.earned_at[:10], fmt="long",
                    lang=self._lang)
            except Exception:
                date_str = achievement.earned_at[:10]
            msg_lines = [
                name,
                "",
                desc,
                "",
                f"{self._tr('تیر', 'Tier')}: {tier_label}",
                f"{self._tr('پاداش XP', 'XP reward')}: {xp_str}",
                f"{self._tr('کسب در', 'Earned on')}: {date_str}",
            ]
            AlertDialog(
                self, title=self._tr("جزئیات دستاورد",
                                       "Achievement details"),
                message="\n".join(msg_lines),
                lang=self._lang, ok_text=self._tr("بستن", "Close"),
            )
        else:
            pct = max(0.0, min(1.0, achievement.progress))
            pct_int = int(pct * 100)
            pct_str = (i18n.to_fa_digits(str(pct_int)) + "٪"
                       if self._lang == "fa" else f"{pct_int}%")
            msg_lines = [
                name,
                "",
                desc,
                "",
                f"{self._tr('تیر', 'Tier')}: {tier_label}",
                f"{self._tr('پاداش XP', 'XP reward')}: {xp_str}",
                f"{self._tr('پیشرفت', 'Progress')}: {pct_str}",
                f"{self._tr('وضعیت', 'Status')}: "
                f"{self._tr('قفل‌شده', 'Locked')}",
            ]
            AlertDialog(
                self, title=self._tr("دستاورد قفل‌شده",
                                       "Achievement locked"),
                message="\n".join(msg_lines),
                lang=self._lang, ok_text=self._tr("بستن", "Close"),
            )

    # ------------------------------------------------------------------
    # Confetti
    # ------------------------------------------------------------------
    def _fire_confetti(self) -> None:
        try:
            Confetti.celebrate(self, duration=2400, particle_count=80)
        except Exception:
            pass
        self._show_toast(self._tr("دستاورد جدید!",
                                    "New achievement!"))

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
    print("AchievementsScreen module: level card + summary + tier "
          "filter + 4-col grid + confetti on earn.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
