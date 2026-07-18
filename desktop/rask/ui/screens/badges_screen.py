"""
rask.ui.screens.badges_screen
=============================

Badges screen — gamification achievements grid.

Displays the 12 milestone badges defined in :data:`config.BADGE_DEFINITIONS`
in a 4-column grid.  Earned badges are shown in full colour with the
earned-date stamp; locked badges are rendered in grayscale with a 🔒
overlay and a progress hint toward the next milestone.

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"نشان‌ها"`` with progress summary
       (e.g. ``"۵ / ۱۲ کسب شده"``)
    2. **Overall progress ring** — large central ring showing the
       percentage of badges earned
    3. **Tier legend** — bronze / silver / gold / platinum colour key
    4. **Badges grid** — 4 columns × 3 rows of :class:`BadgeCard`s
    5. **Tap-to-detail** — tapping an earned badge opens an alert with
       earned date + metadata; tapping a locked badge shows the
       progress toward it

Auto-refresh
------------
Subscribes to ``badge.unlocked`` (fires confetti + toast),
``activity.added`` / ``activity.updated`` / ``activity.deleted`` /
``streak.incremented`` / ``streak.reset`` / ``goal.added`` /
``goal.updated`` / ``goal.deleted`` / ``language.changed`` /
``data.imported`` / ``data.cleared``.
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
from ...services import badge_service, settings_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import GoldButton, GhostButton, TextButton, IconButton
from ..widgets.cards import Card
from ..widgets.badges import TierBadge, TIER_COLORS
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.progress_ring import ProgressRing
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.sliders import ProgressBar
from ..widgets.confetti import Confetti
from ..widgets.dialogs import AlertDialog

__all__ = ["BadgesScreen"]


# =============================================================================
# === Tier labels                                                            ===
# =============================================================================

TIER_LABELS_FA: Dict[str, str] = {
    "bronze": "برنز",
    "silver": "نقره",
    "gold": "طلایی",
    "platinum": "پلاتین",
}
TIER_LABELS_EN: Dict[str, str] = {
    "bronze": "Bronze",
    "silver": "Silver",
    "gold": "Gold",
    "platinum": "Platinum",
}


def _tier_label(tier: str, lang: str) -> str:
    if lang == "fa":
        return TIER_LABELS_FA.get(tier, tier)
    return TIER_LABELS_EN.get(tier, tier)


# =============================================================================
# === Badge grid cell                                                        ===
# =============================================================================

class _BadgeCell(Card):
    """One badge in the grid — circular icon, name, tier colour border."""

    def __init__(
        self,
        master: Any,
        badge: Dict[str, Any],
        progress: Optional[Dict[str, Any]],
        lang: str = "fa",
        on_click: Optional[Callable[[Dict[str, Any]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("padding", config.SPACE_SM)
        super().__init__(master, lang=lang, on_click=(on_click
                                                       and (lambda: on_click(badge))),
                          **kwargs)
        self._badge = badge
        self._lang = lang
        self._progress = progress
        rtl = i18n.is_rtl(lang)
        earned = bool(badge.get("earned"))
        # Grid layout: icon (top), name (middle), tier / status (bottom)
        self.content.grid_columnconfigure(0, weight=1)
        # Icon container (square)
        icon_frame = ctk.CTkFrame(self.content, fg_color="transparent",
                                   height=72)
        icon_frame.grid(row=0, column=0, pady=(0, 4))
        icon_frame.grid_columnconfigure(0, weight=1)
        # Use TierBadge for the icon
        tier = badge.get("tier", "gold")
        icon_name = badge.get("icon") or "trophy"
        tier_badge = TierBadge(
            icon_frame, tier=tier, icon_name=icon_name,
            size=56, earned=earned, lang=lang,
        )
        tier_badge.grid(row=0, column=0)
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
        name = (badge.get("name_fa") if lang == "fa"
                 else badge.get("name_en")) or "—"
        name_label = ctk.CTkLabel(
            self.content, text=name,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=lang),
            text_color=config.TEXT if earned else config.TEXT_DIM,
            wraplength=80, justify="center",
            anchor="center",
        )
        name_label.grid(row=1, column=0, pady=(2, 0))
        # Tier label
        ctk.CTkLabel(
            self.content, text=_tier_label(tier, lang),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=lang),
            text_color=TIER_COLORS.get(tier, config.GOLD)
            if earned else config.TEXT_FAINT,
        ).grid(row=2, column=0, pady=(1, 0))
        # Status row: earned date OR progress %
        if earned:
            earned_at = badge.get("earned_at") or ""
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
        elif progress:
            # Show progress %
            pct = int(progress.get("percent", 0))
            pct_str = (i18n.to_fa_digits(str(pct)) + "٪"
                       if lang == "fa" else f"{pct}%")
            ctk.CTkLabel(
                self.content, text=pct_str,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=lang),
                text_color=config.TEXT_DIM,
            ).grid(row=3, column=0, pady=(1, 0))


# =============================================================================
# === BadgesScreen                                                           ===
# =============================================================================

class BadgesScreen(ctk.CTkFrame):
    """Badges grid screen.

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
        self._badge_cells: List[_BadgeCell] = []
        self._known_earned_keys: set = set()
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
            self, title=i18n.t("badges", self._lang),
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
        # Sections
        self._section_row = 0
        self._build_progress_card()
        self._build_legend()
        self._build_grid()

    def _build_progress_card(self) -> None:
        """Large ring + count summary card."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Ring on one side
        self._progress_ring = ProgressRing(
            card.content, progress=0.0, size=120,
            line_width=10, show_percentage=False,
            animated=True, lang=self._lang, label="0%",
        )
        self._progress_ring.grid(row=0, column=0, padx=8,
                                   rowspan=2, sticky="nsew")
        # Info column
        info = ctk.CTkFrame(card.content, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            info, text=self._tr("badgesEarned", "Badges earned"),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        self._count_label = ctk.CTkLabel(
            info, text="—",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._count_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Subtitle
        self._subtitle_label = ctk.CTkLabel(
            info, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
            anchor="e" if rtl else "w",
        )
        self._subtitle_label.grid(row=2, column=0, sticky="ew", pady=(2, 0))

    def _build_legend(self) -> None:
        """Tier colour legend row."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Center the row
        chips_frame = ctk.CTkFrame(row, fg_color="transparent")
        chips_frame.pack(anchor="center")
        for tier in ("bronze", "silver", "gold", "platinum"):
            chip = ctk.CTkFrame(chips_frame, fg_color="transparent")
            chip.pack(side="right" if rtl else "left", padx=6)
            dot = ctk.CTkFrame(chip, width=10, height=10,
                                fg_color=TIER_COLORS.get(tier, config.GOLD),
                                corner_radius=config.RADIUS_PILL)
            dot.pack(side="right" if rtl else "left", padx=(0, 4))
            ctk.CTkLabel(
                chip, text=_tier_label(tier, self._lang),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).pack(side="right" if rtl else "left")

    def _build_grid(self) -> None:
        """The 4×3 badge grid."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("allBadges", "All badges"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        self._grid_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._grid_frame.grid(row=1, column=0, sticky="ew")
        for i in range(4):
            self._grid_frame.grid_columnconfigure(i, weight=1,
                                                    uniform="badge")

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
            "badge.unlocked",
            "activity.added", "activity.updated", "activity.deleted",
            "streak.incremented", "streak.reset",
            "goal.added", "goal.updated", "goal.deleted",
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
        # Detect newly-earned badges for confetti
        try:
            ev = args[0] if args else None
            if isinstance(ev, dict) and "key" in ev:
                key = ev.get("key")
                if key and key not in self._known_earned_keys:
                    self._fire_confetti()
        except Exception:
            pass
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
        """Rebuild the grid + summary."""
        # Fetch all badges
        try:
            badges = badge_service.list_all()
        except Exception:
            badges = []
        # Update known-earned set (for confetti detection)
        earned_keys = {b.get("key") for b in badges if b.get("earned")}
        # Newly earned (earned now but not in our previous snapshot)
        newly_earned = earned_keys - self._known_earned_keys
        self._known_earned_keys = earned_keys
        # If there are newly-earned badges and we already had data, fire confetti
        if newly_earned and self._badge_cells:
            self._fire_confetti()
        # Update summary
        total = len(badges)
        earned_count = len(earned_keys)
        pct = (earned_count / total) if total > 0 else 0.0
        try:
            self._progress_ring.set_progress(pct, animate=True)
        except Exception:
            pass
        try:
            pct_int = int(pct * 100)
            pct_str = (i18n.to_fa_digits(str(pct_int)) + "٪"
                       if self._lang == "fa" else f"{pct_int}%")
            self._progress_ring.configure(label=pct_str)  # may not work
        except Exception:
            pass
        try:
            earned_str = (i18n.to_fa_digits(str(earned_count))
                          if self._lang == "fa" else str(earned_count))
            total_str = (i18n.to_fa_digits(str(total))
                         if self._lang == "fa" else str(total))
            self._count_label.configure(
                text=f"{earned_str} / {total_str}")
        except Exception:
            pass
        try:
            sub = (self._tr("keepGoing",
                             "Keep logging activities to earn more!")
                   if earned_count < total
                   else self._tr("allEarned",
                                  "All badges earned — congratulations!"))
            self._subtitle_label.configure(text=sub)
        except Exception:
            pass
        # Clear old cells
        for child in self._grid_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._badge_cells = []
        # Build grid (4 columns)
        for i, badge in enumerate(badges):
            row = i // 4
            col = (3 - (i % 4)) if i18n.is_rtl(self._lang) else (i % 4)
            # Compute progress toward locked badge
            progress = None
            if not badge.get("earned"):
                try:
                    progress = badge_service.progress_to_next(
                        badge.get("key", ""))
                except Exception:
                    progress = None
            cell = _BadgeCell(
                self._grid_frame, badge=badge, progress=progress,
                lang=self._lang,
                on_click=self._on_badge_tap,
            )
            cell.grid(row=row, column=col, sticky="nsew",
                       padx=4, pady=4)
            self._badge_cells.append(cell)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_badge_tap(self, badge: Dict[str, Any]) -> None:
        """Show details about a badge (earned or locked)."""
        key = badge.get("key", "")
        name = (badge.get("name_fa") if self._lang == "fa"
                 else badge.get("name_en")) or "—"
        desc = (badge.get("desc_fa") if self._lang == "fa"
                 else badge.get("desc_en")) or ""
        tier = badge.get("tier", "gold")
        if badge.get("earned"):
            earned_at = badge.get("earned_at") or ""
            try:
                date_str = jalali.format_jalali(
                    earned_at[:10], fmt="long", lang=self._lang)
            except Exception:
                date_str = earned_at[:10] if earned_at else "—"
            msg_lines = [
                f"{name}",
                "",
                desc,
                "",
                f"{self._tr('tier', 'Tier')}: {_tier_label(tier, self._lang)}",
                f"{self._tr('earnedOn', 'Earned on')}: {date_str}",
            ]
            # Include metadata if present
            metadata = badge.get("metadata") or {}
            if metadata:
                msg_lines.append("")
                msg_lines.append(self._tr("details", "Details") + ":")
                for k, v in metadata.items():
                    msg_lines.append(f"  • {k}: {v}")
            AlertDialog(
                self, title=self._tr("badgeDetails", "Badge details"),
                message="\n".join(msg_lines),
                lang=self._lang,
                ok_text=self._tr("close", "Close"),
            )
        else:
            # Locked — show progress
            try:
                progress = badge_service.progress_to_next(key) or {}
            except Exception:
                progress = {}
            msg_lines = [
                f"{name}",
                "",
                desc,
                "",
                f"{self._tr('tier', 'Tier')}: {_tier_label(tier, self._lang)}",
                f"{self._tr('status', 'Status')}: "
                f"{self._tr('locked', 'Locked')}",
            ]
            if progress:
                current = int(progress.get("current", 0))
                target = int(progress.get("target", 0))
                pct = int(progress.get("percent", 0))
                remaining = int(progress.get("remaining", 0))
                cur_str = (i18n.to_fa_digits(str(current))
                           if self._lang == "fa" else str(current))
                tgt_str = (i18n.to_fa_digits(str(target))
                           if self._lang == "fa" else str(target))
                pct_str = (i18n.to_fa_digits(str(pct)) + "٪"
                           if self._lang == "fa" else f"{pct}%")
                rem_str = (i18n.to_fa_digits(str(remaining))
                           if self._lang == "fa" else str(remaining))
                msg_lines.extend([
                    "",
                    f"{self._tr('progress', 'Progress')}: {cur_str} / {tgt_str}",
                    f"{self._tr('percent', 'Percent')}: {pct_str}",
                    f"{self._tr('remaining', 'Remaining')}: {rem_str}",
                ])
            AlertDialog(
                self, title=self._tr("badgeLocked", "Badge locked"),
                message="\n".join(msg_lines),
                lang=self._lang,
                ok_text=self._tr("close", "Close"),
            )

    # ------------------------------------------------------------------
    # Confetti
    # ------------------------------------------------------------------
    def _fire_confetti(self) -> None:
        """Trigger a confetti burst + toast."""
        try:
            Confetti.celebrate(self, duration=2400, particle_count=80)
        except Exception:
            pass
        self._show_toast(self._tr("badgeUnlocked", "Badge unlocked!"))

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
                                                "kind": "achievement"})
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
    print("BadgesScreen module: ring + legend + 4×3 grid + confetti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
