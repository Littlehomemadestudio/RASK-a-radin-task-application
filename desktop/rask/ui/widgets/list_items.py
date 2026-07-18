"""
rask.ui.widgets.list_items
==========================

List-item row widgets — base ``ListItem`` plus domain-specific variants
for activities, goals, templates, reminders, badges, categories.

All items support optional swipe-to-delete (right-to-left swipe reveals
a delete button), long-press menu (via callback), and click to open.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .badges import CategoryBadge, TierBadge, StreakBadge, CountBadge
from .toggles import Toggle
from .sliders import ProgressBar

__all__ = [
    "ListItem", "ActivityListItem", "GoalListItem",
    "TemplateListItem", "ReminderListItem", "BadgeListItem",
    "CategoryListItem",
]


# =============================================================================
# === Base ListItem                                                         ===
# =============================================================================

class ListItem(ctk.CTkFrame):
    """Base row: leading icon, title, subtitle, trailing widget.

    Parameters
    ----------
    title
        Primary text.
    subtitle
        Secondary text below the title.
    leading
        Either an icon name (string) or a widget instance placed in the
        leading slot.
    trailing
        Optional widget placed at the trailing edge.
    on_click / on_long_press
        Callbacks.
    swipe_to_delete
        If True, a left-swipe reveals a delete button.
    on_delete
        Callback invoked when the delete button is tapped.
    """

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        subtitle: str = "",
        leading: Optional[Any] = None,
        trailing: Optional[Any] = None,
        on_click: Optional[Callable[[], Any]] = None,
        on_long_press: Optional[Callable[[], Any]] = None,
        swipe_to_delete: bool = False,
        on_delete: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        height: int = 64,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._on_click = on_click
        self._on_long_press = on_long_press
        self._on_delete = on_delete
        self._swipe_enabled = swipe_to_delete
        self._lang = lang
        self._base_bg = config.CHARCOAL
        self._hover_bg = config.SURFACE
        self._long_press_job = None
        self._drag_start_x: Optional[int] = None
        self._build(title, subtitle, leading, trailing)
        self._bind_events()

    # ------------------------------------------------------------------
    def _build(
        self,
        title: str,
        subtitle: Optional[str],
        leading: Optional[Any],
        trailing: Optional[Any],
    ) -> None:
        rtl = i18n.is_rtl(self._lang)
        self.grid_columnconfigure(1, weight=1)
        # Leading
        if leading is not None:
            if isinstance(leading, str):
                icon = ctk.CTkLabel(self, text="", width=40, height=40,
                                     fg_color="transparent")
                img = _icons.icon(leading, 24, color=config.GOLD)
                if img is not None:
                    icon.configure(image=img)
                else:
                    icon.configure(text=_icons.icon_glyph(leading),
                                    text_color=config.GOLD,
                                    font=_theme.theme.font(
                                        size=20, weight="bold", lang="en"))
                icon.grid(row=0, column=0, padx=(12, 6), pady=12)
            else:
                leading.grid(in_=self, row=0, column=0,
                              padx=(12, 6), pady=12)
        else:
            # Empty leading slot — keeps grid stable
            ctk.CTkFrame(self, width=0, height=0,
                         fg_color="transparent").grid(row=0, column=0)
        # Title + subtitle column
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=4, pady=10)
        info.grid_columnconfigure(0, weight=1)
        self._title_label = ctk.CTkLabel(
            info, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        )
        self._title_label.grid(row=0, column=0, sticky="ew")
        if subtitle:
            self._subtitle_label = ctk.CTkLabel(
                info, text=subtitle,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
                anchor="e" if rtl else "w",
            )
            self._subtitle_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Trailing
        if trailing is not None:
            trailing.grid(in_=self, row=0, column=2,
                           padx=(6, 12), pady=12)

    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        try:
            self.bind("<Enter>", self._on_enter, add="+")
            self.bind("<Leave>", self._on_leave, add="+")
            self.bind("<ButtonPress-1>", self._on_press, add="+")
            self.bind("<ButtonRelease-1>", self._on_release, add="+")
            if self._swipe_enabled:
                self.bind("<B1-Motion>", self._on_drag, add="+")
            for child in self.winfo_children():
                child.bind("<Enter>", self._on_enter, add="+")
                child.bind("<Leave>", self._on_leave, add="+")
                child.bind("<ButtonPress-1>", self._on_press, add="+")
                child.bind("<ButtonRelease-1>", self._on_release, add="+")
                if self._swipe_enabled:
                    child.bind("<B1-Motion>", self._on_drag, add="+")
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
        self._cancel_long_press()

    def _on_press(self, evt: Any = None) -> None:
        if self._on_long_press:
            self._long_press_job = self.after(600, self._fire_long_press)
        if self._swipe_enabled and evt is not None:
            self._drag_start_x = evt.x_root

    def _on_release(self, _evt: Any = None) -> None:
        self._cancel_long_press()
        if self._drag_start_x is not None:
            # Was a swipe — let _on_drag handle it
            self._drag_start_x = None
            return
        if self._on_click:
            try:
                self._on_click()
            except Exception:
                pass

    def _on_drag(self, evt: Any = None) -> None:
        if not self._swipe_enabled or self._drag_start_x is None:
            return
        try:
            dx = evt.x_root - self._drag_start_x
            # For RTL (Persian), swipe right-to-left (negative dx) reveals
            # delete; for LTR, swipe left-to-right (positive dx) reveals.
            rtl = i18n.is_rtl(self._lang)
            threshold = 60
            if (rtl and dx < -threshold) or (not rtl and dx > threshold):
                self._reveal_delete()
            elif (rtl and dx > threshold) or (not rtl and dx < -threshold):
                # Reverse swipe — also delete in LTR layout
                if not rtl:
                    self._reveal_delete()
        except Exception:
            pass

    def _reveal_delete(self) -> None:
        if not self._on_delete:
            return
        try:
            self.configure(fg_color=config.DANGER_DIM)
            btn = ctk.CTkButton(
                self, text="حذف" if self._lang == "fa" else "Delete",
                command=self._do_delete,
                fg_color=config.DANGER, hover_color=config.DANGER_DIM,
                text_color="#FFFFFF",
                corner_radius=config.RADIUS_SM, height=32,
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="bold", lang=self._lang),
            )
            btn.place(relx=0.5, rely=0.5, anchor="center")
            # Auto-hide after 3 seconds
            self.after(3000, lambda: btn.destroy() if btn.winfo_exists() else None)
        except Exception:
            pass
        self._drag_start_x = None

    def _do_delete(self) -> None:
        if self._on_delete:
            try:
                self._on_delete()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass

    def _cancel_long_press(self) -> None:
        if self._long_press_job:
            try:
                self.after_cancel(self._long_press_job)
            except Exception:
                pass
            self._long_press_job = None

    def _fire_long_press(self) -> None:
        self._long_press_job = None
        if self._on_long_press:
            try:
                self._on_long_press()
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def title(self) -> str:
        return self._title_label.cget("text")

    def set_title(self, title: str) -> None:
        try:
            self._title_label.configure(text=title)
        except Exception:
            pass


# =============================================================================
# === ActivityListItem                                                      ===
# =============================================================================

class ActivityListItem(ListItem):
    """Activity row: category color stripe, title, duration, time, tags."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        category_name: str = "",
        category_color: str = config.GOLD,
        duration: str = "",
        time_str: str = "",
        tags: Optional[list[str]] = None,
        on_click: Optional[Callable[[], Any]] = None,
        on_delete: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        subtitle_parts = []
        if time_str:
            subtitle_parts.append(time_str)
        if category_name:
            subtitle_parts.append(category_name)
        subtitle = " · ".join(subtitle_parts)
        super().__init__(master, title=title, subtitle=subtitle,
                         leading=None, trailing=None,
                         on_click=on_click, swipe_to_delete=on_delete is not None,
                         on_delete=on_delete, lang=lang, **kwargs)
        rtl = i18n.is_rtl(lang)
        # Override leading with a color stripe + dot
        # Already-built children: replace the empty leading slot
        stripe = ctk.CTkFrame(self, width=4, fg_color=category_color)
        stripe.grid(row=0, column=0, padx=(0, 0), pady=8, sticky="ns")
        # Add duration as trailing label
        dur_label = ctk.CTkLabel(
            self, text=duration,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.GOLD,
        )
        dur_label.grid(row=0, column=2, padx=(6, 12), pady=12)
        # Append tags below subtitle if provided
        if tags:
            tag_row = ctk.CTkFrame(self, fg_color="transparent")
            tag_row.grid(row=1, column=0, columnspan=3, sticky="ew",
                         padx=12, pady=(0, 8))
            for tag in tags[:4]:
                from .badges import TagChip
                chip = TagChip(tag_row, text=tag, lang=lang)
                chip.pack(side="right" if rtl else "left", padx=2)


# =============================================================================
# === GoalListItem                                                          ===
# =============================================================================

class GoalListItem(ListItem):
    """Goal row: title, period, mini progress bar."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        period: str = "",
        progress: float = 0.0,
        current_min: int = 0,
        target_min: int = 0,
        on_click: Optional[Callable[[], Any]] = None,
        on_delete: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        subtitle_parts = [period] if period else []
        if target_min:
            cur = i18n.to_fa_digits(current_min) if lang == "fa" else str(current_min)
            tgt = i18n.to_fa_digits(target_min) if lang == "fa" else str(target_min)
            unit = "دقیقه" if lang == "fa" else "min"
            subtitle_parts.append(f"{cur} / {tgt} {unit}")
        super().__init__(master, title=title,
                         subtitle=" · ".join(subtitle_parts),
                         leading="goals", on_click=on_click,
                         swipe_to_delete=on_delete is not None,
                         on_delete=on_delete, lang=lang, **kwargs)
        # Mini progress bar at the bottom
        bar = ProgressBar(self, value=progress, height=3)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew",
                  padx=12, pady=(0, 8))


# =============================================================================
# === TemplateListItem                                                      ===
# =============================================================================

class TemplateListItem(ListItem):
    """Template row: title, duration, shortcut key, use count."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        duration_min: int = 0,
        shortcut: Optional[str] = None,
        use_count: int = 0,
        on_click: Optional[Callable[[], Any]] = None,
        on_delete: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        subtitle_parts = []
        if duration_min:
            dur = i18n.to_fa_digits(duration_min) if lang == "fa" else str(duration_min)
            unit = "دقیقه" if lang == "fa" else "min"
            subtitle_parts.append(f"{dur} {unit}")
        if use_count:
            uc = i18n.to_fa_digits(use_count) if lang == "fa" else str(use_count)
            uses_word = "استفاده" if lang == "fa" else "uses"
            subtitle_parts.append(f"{uc} {uses_word}")
        super().__init__(master, title=title,
                         subtitle=" · ".join(subtitle_parts),
                         leading="plus", on_click=on_click,
                         swipe_to_delete=on_delete is not None,
                         on_delete=on_delete, lang=lang, **kwargs)
        # Shortcut key chip
        if shortcut:
            sk = ctk.CTkFrame(self, width=26, height=26,
                              fg_color=config.SURFACE_HI,
                              corner_radius=config.RADIUS_SM,
                              border_width=1, border_color=config.GOLD_DIM)
            sk.grid(row=0, column=2, padx=(6, 4), pady=12)
            sk.grid_propagate(False)
            ctk.CTkLabel(
                sk, text=shortcut,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang="en"),
                text_color=config.GOLD,
            ).pack(expand=True, fill="both")


# =============================================================================
# === ReminderListItem                                                      ===
# =============================================================================

class ReminderListItem(ListItem):
    """Reminder row: bell icon, time + days, toggle."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        time_str: str = "",
        days: str = "",
        enabled: bool = True,
        on_toggle: Optional[Callable[[bool], Any]] = None,
        on_click: Optional[Callable[[], Any]] = None,
        on_delete: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        subtitle_parts = []
        if time_str:
            subtitle_parts.append(time_str)
        if days:
            subtitle_parts.append(days)
        super().__init__(master, title=title,
                         subtitle=" · ".join(subtitle_parts),
                         leading="bell", on_click=on_click,
                         swipe_to_delete=on_delete is not None,
                         on_delete=on_delete, lang=lang, **kwargs)
        # Toggle in trailing slot
        t = Toggle(self, on_change=on_toggle, lang=lang, height=28)
        t.value = enabled
        t.grid(row=0, column=2, padx=(6, 12), pady=12)


# =============================================================================
# === BadgeListItem                                                         ===
# =============================================================================

class BadgeListItem(ListItem):
    """Badge row: tier-colored icon, name, description, earned state."""

    def __init__(
        self,
        master: Any = None,
        name: str = "",
        description: str = "",
        tier: str = "gold",
        icon_name: str = "trophy",
        earned: bool = False,
        on_click: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        super().__init__(master, title=name, subtitle=description,
                         leading=None, on_click=on_click, lang=lang, **kwargs)
        # Replace leading with TierBadge
        tier_badge = TierBadge(self, tier=tier, icon_name=icon_name,
                                size=40, earned=earned, lang=lang)
        tier_badge.grid(row=0, column=0, padx=(8, 6), pady=10)


# =============================================================================
# === CategoryListItem                                                      ===
# =============================================================================

class CategoryListItem(ListItem):
    """Category row: color swatch, name, activity count."""

    def __init__(
        self,
        master: Any = None,
        name: str = "",
        color: str = config.GOLD,
        activity_count: int = 0,
        on_click: Optional[Callable[[], Any]] = None,
        on_delete: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        count_str = (i18n.to_fa_digits(activity_count) if lang == "fa"
                     else str(activity_count))
        activities_word = "فعالیت" if lang == "fa" else "activities"
        subtitle = f"{count_str} {activities_word}"
        super().__init__(master, title=name, subtitle=subtitle,
                         leading=None, on_click=on_click,
                         swipe_to_delete=on_delete is not None,
                         on_delete=on_delete, lang=lang, **kwargs)
        # Replace leading with a color swatch
        swatch = ctk.CTkFrame(self, width=28, height=28,
                              fg_color=color,
                              corner_radius=14)
        swatch.grid(row=0, column=0, padx=(12, 6), pady=12)


def _self_test() -> int:
    classes = [ListItem, ActivityListItem, GoalListItem, TemplateListItem,
                ReminderListItem, BadgeListItem, CategoryListItem]
    print(f"List items module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
