"""
rask.ui.widgets.cards
=====================

Card-style containers for the Rask gold-on-dark theme.

All cards derive from :class:`Card` and add hover lightening,
click/long-press handlers, and a consistent surface background with
rounded corners and a subtle border.

Variants
--------
``Card``          — base card (title + content frame)
``StatCard``      — large stat + delta + sparkline
``ActivityCard``  — one activity (title, badge, duration, time, notes)
``GoalCard``      — goal with progress ring + streak
``TemplateCard``  — template with use button + shortcut key
``BadgeCard``     — badge with icon, tier color, earned/locked
``ReminderCard``  — reminder with time, days, toggle
``SettingCard``   — setting row with trailing widget
``SummaryCard``   — big number + label + optional subtitle
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .progress_ring import ProgressRing
from .toggles import Toggle
from .buttons import IconButton, GoldButton
from .badges import CategoryBadge, TierBadge, StreakBadge

__all__ = [
    "Card", "StatCard", "ActivityCard", "GoalCard", "TemplateCard",
    "BadgeCard", "ReminderCard", "SettingCard", "SummaryCard",
]


# =============================================================================
# === Base Card                                                             ===
# =============================================================================

class Card(ctk.CTkFrame):
    """Base card: surface background, rounded corners, subtle border.

    Provides hover lightening, click and long-press callbacks, and an
    optional title bar.

    Parameters
    ----------
    title
        Optional header text shown at the top.
    on_click
        Callback invoked on a single left-click.
    on_long_press
        Callback invoked after a 600ms press-and-hold.
    lang
        Layout direction ("fa" for RTL, "en" for LTR).
    """

    def __init__(
        self,
        master: Any = None,
        title: Optional[str] = None,
        on_click: Optional[Callable[[], Any]] = None,
        on_long_press: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        width: Optional[int] = None,
        height: Optional[int] = None,
        padding: int = config.SPACE_LG,
        radius: int = config.RADIUS_MD,
        elevation: int = config.ELEVATION_1,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.DIVIDER)
        kwargs.setdefault("corner_radius", radius)
        if width is not None:
            kwargs.setdefault("width", width)
        if height is not None:
            kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._on_click = on_click
        self._on_long_press = on_long_press
        self._lang = lang
        self._base_bg = config.CHARCOAL
        self._hover_bg = config.SURFACE
        self._title_label: Optional[ctk.CTkLabel] = None
        self._content: Optional[ctk.CTkFrame] = None
        self._long_press_job = None
        self._build(padding, title)
        self._bind_events()

    def _build(self, padding: int, title: Optional[str]) -> None:
        # Top-level grid: optional title row + content row
        self.grid_columnconfigure(0, weight=1)
        if title:
            self._title_label = ctk.CTkLabel(
                self, text=title,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                        weight="bold", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if i18n.is_rtl(self._lang) else "w",
            )
            self._title_label.grid(row=0, column=0, sticky="ew",
                                    padx=padding, pady=(padding, padding // 2))
            content_row = 1
        else:
            content_row = 0
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=content_row, column=0, sticky="nsew",
                            padx=padding,
                            pady=(0 if title else padding, padding))
        self.grid_rowconfigure(content_row, weight=1)

    @property
    def content(self) -> ctk.CTkFrame:
        """Return the inner content frame for child widgets."""
        return self._content  # type: ignore[return-value]

    def _bind_events(self) -> None:
        try:
            self.bind("<Enter>", self._on_enter, add="+")
            self.bind("<Leave>", self._on_leave, add="+")
            self.bind("<ButtonPress-1>", self._on_press, add="+")
            self.bind("<ButtonRelease-1>", self._on_release, add="+")
            for child in self.winfo_children():
                child.bind("<Enter>", self._on_enter, add="+")
                child.bind("<Leave>", self._on_leave, add="+")
                child.bind("<ButtonPress-1>", self._on_press, add="+")
                child.bind("<ButtonRelease-1>", self._on_release, add="+")
        except Exception:
            pass

    def _on_enter(self, _evt: Any = None) -> None:
        if self._on_click or self._on_long_press:
            try:
                self.configure(fg_color=self._hover_bg)
            except Exception:
                pass

    def _on_leave(self, _evt: Any = None) -> None:
        try:
            self.configure(fg_color=self._base_bg)
        except Exception:
            pass
        if self._long_press_job:
            try:
                self.after_cancel(self._long_press_job)
            except Exception:
                pass
            self._long_press_job = None

    def _on_press(self, _evt: Any = None) -> None:
        if self._on_long_press:
            self._long_press_job = self.after(600, self._fire_long_press)

    def _on_release(self, _evt: Any = None) -> None:
        if self._long_press_job:
            try:
                self.after_cancel(self._long_press_job)
            except Exception:
                pass
            self._long_press_job = None
            if self._on_click:
                try:
                    self._on_click()
                except Exception:
                    pass

    def _fire_long_press(self) -> None:
        self._long_press_job = None
        if self._on_long_press:
            try:
                self._on_long_press()
            except Exception:
                pass


# =============================================================================
# === StatCard                                                              ===
# =============================================================================

class StatCard(Card):
    """Large stat display with label, value, delta vs last period, sparkline."""

    def __init__(
        self,
        master: Any = None,
        label: str = "",
        value: str = "",
        delta: Optional[str] = None,
        delta_positive: bool = True,
        sparkline_data: Optional[list[float]] = None,
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click, **kwargs)
        from .charts import Sparkline
        rtl = i18n.is_rtl(lang)
        # Value (large gold)
        self._value_label = ctk.CTkLabel(
            self._content, text=value,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._value_label.pack(anchor="e" if rtl else "w")
        # Label (small dim)
        self._label_label = ctk.CTkLabel(
            self._content, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        )
        self._label_label.pack(anchor="e" if rtl else "w", pady=(2, 0))
        # Delta row (sparkline + percentage)
        delta_row = ctk.CTkFrame(self._content, fg_color="transparent")
        delta_row.pack(fill="x", pady=(8, 0))
        if sparkline_data:
            sp = Sparkline(delta_row, data=sparkline_data, width=80,
                            height=24, lang=lang)
            sp.pack(side="right" if rtl else "left", padx=2)
        if delta:
            color = config.SUCCESS if delta_positive else config.DANGER
            sign = "▲" if delta_positive else "▼"
            delta_text = f"{sign} {delta}" if lang == "en" else f"{delta} {sign}"
            dlabel = ctk.CTkLabel(
                delta_row, text=delta_text,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=lang),
                text_color=color,
            )
            dlabel.pack(side="right" if rtl else "left", padx=4)

    def set_value(self, value: str) -> None:
        try:
            self._value_label.configure(text=value)
        except Exception:
            pass

    def set_label(self, label: str) -> None:
        try:
            self._label_label.configure(text=label)
        except Exception:
            pass


# =============================================================================
# === ActivityCard                                                          ===
# =============================================================================

class ActivityCard(Card):
    """One activity row: title, category badge, duration, time, notes preview."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        category_name: str = "",
        category_color: str = config.GOLD,
        duration: str = "",
        time_str: str = "",
        notes: str = "",
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click,
                          padding=config.SPACE_MD, **kwargs)
        rtl = i18n.is_rtl(lang)
        # Top row: title + duration
        top = ctk.CTkFrame(self._content, fg_color="transparent")
        top.pack(fill="x")
        self._title_label = ctk.CTkLabel(
            top, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        )
        self._title_label.pack(side="right" if rtl else "left", fill="x",
                                expand=True)
        self._duration_label = ctk.CTkLabel(
            top, text=duration,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.GOLD,
        )
        self._duration_label.pack(side="left" if rtl else "right", padx=(8, 0))
        # Bottom row: badge + time
        bottom = ctk.CTkFrame(self._content, fg_color="transparent")
        bottom.pack(fill="x", pady=(4, 0))
        # Category color stripe
        stripe = ctk.CTkFrame(bottom, width=4, fg_color=category_color)
        stripe.pack(side="right" if rtl else "left", fill="y", padx=(0, 6))
        self._badge = CategoryBadge(bottom, text=category_name,
                                     color=category_color, lang=lang)
        self._badge.pack(side="right" if rtl else "left", padx=2)
        if time_str:
            self._time_label = ctk.CTkLabel(
                bottom, text=time_str,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=lang),
                text_color=config.TEXT_FAINT,
            )
            self._time_label.pack(side="left" if rtl else "right", padx=4)
        # Notes preview
        if notes:
            self._notes_label = ctk.CTkLabel(
                self._content, text=notes,
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=lang),
                text_color=config.TEXT_DIM,
                anchor="e" if rtl else "w",
                wraplength=380,
            )
            self._notes_label.pack(fill="x", pady=(4, 0))


# =============================================================================
# === GoalCard                                                              ===
# =============================================================================

class GoalCard(Card):
    """Goal with progress ring + streak count."""

    def __init__(
        self,
        master: Any = None,
        period: str = "",
        current_min: int = 0,
        target_min: int = 120,
        streak: int = 0,
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click,
                          padding=config.SPACE_MD, **kwargs)
        rtl = i18n.is_rtl(lang)
        # Ring on one side
        ring_size = 64
        pct = current_min / max(1, target_min)
        ring = ProgressRing(self._content, progress=pct, size=ring_size,
                            line_width=6, show_percentage=True,
                            label=f"{int(pct * 100)}%", lang=lang)
        ring.pack(side="right" if rtl else "left", padx=4)
        # Info on the other side
        info = ctk.CTkFrame(self._content, fg_color="transparent")
        info.pack(side="right" if rtl else "left", fill="both",
                   expand=True, padx=8)
        self._period_label = ctk.CTkLabel(
            info, text=period,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        )
        self._period_label.pack(anchor="e" if rtl else "w")
        cur_str = i18n.to_fa_digits(current_min) if lang == "fa" else str(current_min)
        tgt_str = i18n.to_fa_digits(target_min) if lang == "fa" else str(target_min)
        unit = "دقیقه" if lang == "fa" else "min"
        progress_text = f"{cur_str} / {tgt_str} {unit}"
        self._progress_label = ctk.CTkLabel(
            info, text=progress_text,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._progress_label.pack(anchor="e" if rtl else "w", pady=(2, 0))
        if streak > 0:
            streak_badge = StreakBadge(info, days=streak, lang=lang)
            streak_badge.pack(anchor="e" if rtl else "w", pady=(4, 0))


# =============================================================================
# === TemplateCard                                                          ===
# =============================================================================

class TemplateCard(Card):
    """Template card with use button + shortcut key."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        category_name: str = "",
        category_color: str = config.GOLD,
        duration_min: int = 0,
        shortcut: Optional[str] = None,
        use_count: int = 0,
        lang: str = "fa",
        on_use: Optional[Callable[[], Any]] = None,
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click,
                          padding=config.SPACE_MD, **kwargs)
        rtl = i18n.is_rtl(lang)
        # Title row
        self._title_label = ctk.CTkLabel(
            self._content, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        )
        self._title_label.pack(anchor="e" if rtl else "w")
        # Meta row: duration, use count, shortcut
        meta = ctk.CTkFrame(self._content, fg_color="transparent")
        meta.pack(fill="x", pady=(2, 0))
        if duration_min:
            dur_text = (f"{i18n.to_fa_digits(duration_min)} دقیقه"
                        if lang == "fa" else f"{duration_min} min")
            ctk.CTkLabel(
                meta, text=dur_text,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=lang),
                text_color=config.TEXT_DIM,
            ).pack(side="right" if rtl else "left", padx=(0, 6))
        if use_count:
            uc_text = (f"×{i18n.to_fa_digits(use_count)}"
                       if lang == "fa" else f"×{use_count}")
            ctk.CTkLabel(
                meta, text=uc_text,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=lang),
                text_color=config.GOLD,
            ).pack(side="right" if rtl else "left", padx=(0, 6))
        # Use button
        if on_use:
            use_btn = GoldButton(
                self._content, text="ثبت" if lang == "fa" else "Use",
                command=on_use, lang=lang,
                height=30, font_size=config.FONT_SIZE_SMALL,
            )
            use_btn.pack(side="left" if rtl else "right", pady=(4, 0))
        # Shortcut key (k-yellow square)
        if shortcut:
            sk = ctk.CTkFrame(
                meta, width=22, height=22,
                fg_color=config.SURFACE_HI,
                corner_radius=config.RADIUS_SM,
                border_width=1, border_color=config.GOLD_DIM,
            )
            sk.pack(side="left" if rtl else "right", padx=2)
            ctk.CTkLabel(
                sk, text=shortcut,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang="en"),
                text_color=config.GOLD,
            ).pack(expand=True, fill="both")


# =============================================================================
# === BadgeCard                                                             ===
# =============================================================================

class BadgeCard(Card):
    """Badge with icon, tier color, earned/locked state."""

    def __init__(
        self,
        master: Any = None,
        name: str = "",
        description: str = "",
        icon_name: str = "trophy",
        tier: str = "gold",
        earned: bool = False,
        progress: Optional[float] = None,
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click,
                          padding=config.SPACE_MD, **kwargs)
        rtl = i18n.is_rtl(lang)
        # Tier icon on one side
        tier_badge = TierBadge(self._content, tier=tier,
                                icon_name=icon_name, size=48,
                                earned=earned, lang=lang)
        tier_badge.pack(side="right" if rtl else "left", padx=4)
        # Info on the other side
        info = ctk.CTkFrame(self._content, fg_color="transparent")
        info.pack(side="right" if rtl else "left", fill="both",
                   expand=True, padx=8)
        ctk.CTkLabel(
            info, text=name,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.TEXT if earned else config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).pack(anchor="e" if rtl else "w")
        ctk.CTkLabel(
            info, text=description,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
            wraplength=240,
        ).pack(anchor="e" if rtl else "w", pady=(2, 0))
        if not earned and progress is not None:
            from .sliders import ProgressBar
            bar = ProgressBar(info, value=progress, height=4)
            bar.pack(fill="x", pady=(4, 0))
            pct_text = f"{int(progress * 100)}٪" if lang == "fa" else f"{int(progress*100)}%"
            ctk.CTkLabel(
                info, text=pct_text,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=lang),
                text_color=config.GOLD,
                anchor="e" if rtl else "w",
            ).pack(anchor="e" if rtl else "w", pady=(2, 0))


# =============================================================================
# === ReminderCard                                                          ===
# =============================================================================

class ReminderCard(Card):
    """Reminder with time, days, toggle."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        time_str: str = "",
        days: str = "",
        enabled: bool = True,
        lang: str = "fa",
        on_toggle: Optional[Callable[[bool], Any]] = None,
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click,
                          padding=config.SPACE_MD, **kwargs)
        rtl = i18n.is_rtl(lang)
        # Icon
        icon = ctk.CTkLabel(
            self._content, text="",
            width=32, height=32,
            fg_color="transparent",
        )
        img = _icons.icon("bell", 22, color=config.GOLD if enabled else config.TEXT_FAINT)
        if img is not None:
            icon.configure(image=img)
        else:
            icon.configure(text=_icons.icon_glyph("bell"),
                            text_color=config.GOLD if enabled else config.TEXT_FAINT)
        icon.pack(side="right" if rtl else "left", padx=2)
        # Info column
        info = ctk.CTkFrame(self._content, fg_color="transparent")
        info.pack(side="right" if rtl else "left", fill="both",
                   expand=True, padx=8)
        ctk.CTkLabel(
            info, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.TEXT if enabled else config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).pack(anchor="e" if rtl else "w")
        meta_text = " · ".join(s for s in (time_str, days) if s)
        ctk.CTkLabel(
            info, text=meta_text,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).pack(anchor="e" if rtl else "w", pady=(2, 0))
        # Toggle
        self._toggle = Toggle(
            self._content, on_change=on_toggle, lang=lang,
            height=30,
        )
        self._toggle.value = enabled
        self._toggle.pack(side="left" if rtl else "right", padx=4)


# =============================================================================
# === SettingCard                                                           ===
# =============================================================================

class SettingCard(Card):
    """Setting row: title + subtitle + trailing widget."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        subtitle: str = "",
        trailing: Optional[Any] = None,
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click,
                          padding=config.SPACE_MD, **kwargs)
        rtl = i18n.is_rtl(lang)
        info = ctk.CTkFrame(self._content, fg_color="transparent")
        info.pack(side="right" if rtl else "left", fill="both",
                   expand=True)
        ctk.CTkLabel(
            info, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).pack(anchor="e" if rtl else "w")
        if subtitle:
            ctk.CTkLabel(
                info, text=subtitle,
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=lang),
                text_color=config.TEXT_DIM,
                anchor="e" if rtl else "w",
                wraplength=260,
            ).pack(anchor="e" if rtl else "w", pady=(2, 0))
        if trailing is not None:
            trailing.pack(in_=self._content,
                            side="left" if rtl else "right",
                            padx=4)


# =============================================================================
# === SummaryCard                                                           ===
# =============================================================================

class SummaryCard(Card):
    """Big number + label + optional subtitle (used for stats hero)."""

    def __init__(
        self,
        master: Any = None,
        value: str = "",
        label: str = "",
        subtitle: str = "",
        color: str = config.GOLD,
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click,
                          padding=config.SPACE_LG, **kwargs)
        rtl = i18n.is_rtl(lang)
        self._value_label = ctk.CTkLabel(
            self._content, text=value,
            font=_theme.theme.font(size=config.FONT_SIZE_DISPLAY,
                                    weight="bold", lang=lang),
            text_color=color,
            anchor="e" if rtl else "w",
        )
        self._value_label.pack(anchor="e" if rtl else "w")
        ctk.CTkLabel(
            self._content, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).pack(anchor="e" if rtl else "w", pady=(4, 0))
        if subtitle:
            ctk.CTkLabel(
                self._content, text=subtitle,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=lang),
                text_color=config.TEXT_DIM,
                anchor="e" if rtl else "w",
            ).pack(anchor="e" if rtl else "w", pady=(2, 0))

    def set_value(self, v: str) -> None:
        try:
            self._value_label.configure(text=v)
        except Exception:
            pass


def _self_test() -> int:
    classes = [Card, StatCard, ActivityCard, GoalCard, TemplateCard,
                BadgeCard, ReminderCard, SettingCard, SummaryCard]
    print(f"Cards module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
