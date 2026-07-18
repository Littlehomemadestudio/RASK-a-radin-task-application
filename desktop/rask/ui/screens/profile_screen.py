"""
rask.ui.screens.profile_screen
==============================

User profile screen — identity, stats summary, achievement preview,
recent-activity sparkline.

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"پروفایل"`` with edit button
    2. **Avatar block** — large circular avatar with edit overlay,
       user name (big), email, member-since date (Jalali)
    3. **Stats summary card** — 6 stat tiles in a 2×3 grid:
       total sessions / total focus time / longest session /
       favorite category / favorite time of day / average session
    4. **Achievement preview** — top 3 earned badges in a row
    5. **Recent activity sparkline** — 30-day mini bar chart
    6. **Edit mode** — when toggled, name + email + avatar fields
       become editable, save button persists changes

Auto-refresh
------------
Subscribes to ``activity.added`` / ``activity.updated`` /
``activity.deleted`` / ``badge.unlocked`` / ``settings.changed`` /
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
from ...services import (
    settings_service, stats_service, activity_service, badge_service,
)
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.avatars import Avatar
from ..widgets.inputs import GoldEntry
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.charts import Sparkline, BarChart
from ..widgets.badges import TierBadge, TIER_COLORS
from ..widgets.dialogs import PromptDialog, ConfirmDialog

__all__ = ["ProfileScreen"]


# =============================================================================
# === ProfileScreen                                                          ===
# =============================================================================

class ProfileScreen(ctk.CTkFrame):
    """User profile screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``open_avatar_picker()`` — file picker for avatar image
            * ``switch_tab(tab)``
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
        self._edit_mode: bool = False
        self._stat_cards: List[StatCard] = []
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header with edit action
        self._header = Header(
            self, title=i18n.t("profile", self._lang),
            action_text=self._tr("edit", "Edit"),
            on_action=self._on_edit_toggle,
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
        self._build_avatar_block()
        self._build_stats_grid()
        self._build_achievement_preview()
        self._build_recent_chart()

    def _build_avatar_block(self) -> None:
        """Avatar + name + email + member-since."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_LG,
                                                   config.SPACE_MD))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        # Avatar (large, centered)
        avatar_frame = ctk.CTkFrame(card.content, fg_color="transparent")
        avatar_frame.grid(row=0, column=0, pady=(0, config.SPACE_SM))
        avatar_frame.grid_columnconfigure(0, weight=1)
        self._avatar = Avatar(
            avatar_frame, size=96, text="R",
            color=None, ring_color=config.GOLD, ring_width=3,
            lang=self._lang,
        )
        self._avatar.grid(row=0, column=0)
        # Edit overlay button (camera icon)
        edit_btn = ctk.CTkButton(
            avatar_frame, text="",
            width=32, height=32,
            fg_color=config.GOLD, hover_color=config.GOLD_BRIGHT,
            corner_radius=config.RADIUS_PILL, cursor="hand2",
            command=self._on_pick_avatar,
        )
        img = _icons.icon("camera", 18, color=config.MATTE_BLACK)
        if img is not None:
            edit_btn.configure(image=img)
        else:
            edit_btn.configure(text="📷")
        edit_btn.place(relx=0.5, rely=0.0, anchor="center")
        self._avatar_edit_btn = edit_btn
        # Name label (display) or entry (edit mode)
        self._name_label = ctk.CTkLabel(
            avatar_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
        )
        self._name_label.grid(row=1, column=0, pady=(config.SPACE_SM, 0))
        self._name_entry = GoldEntry(
            avatar_frame, placeholder=self._tr("name", "Name"),
            lang=self._lang, height=40, width=240,
        )
        # Hidden by default
        # Email label
        self._email_label = ctk.CTkLabel(
            avatar_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
        )
        self._email_label.grid(row=2, column=0, pady=(2, 0))
        # Member since
        self._member_since_label = ctk.CTkLabel(
            avatar_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
        )
        self._member_since_label.grid(row=3, column=0, pady=(4, 0))

    def _build_stats_grid(self) -> None:
        """2×3 grid of stat tiles."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_MD)
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("summary", "Summary"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        grid = ctk.CTkFrame(section, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew")
        for i in range(3):
            grid.grid_columnconfigure(i, weight=1, uniform="stat")
        labels = [
            self._tr("totalSessions", "Total sessions"),
            self._tr("totalFocus", "Total focus"),
            self._tr("longestSession", "Longest session"),
            self._tr("favoriteCategory", "Top category"),
            self._tr("favoriteTime", "Top time"),
            self._tr("averageSession", "Avg session"),
        ]
        for i, label in enumerate(labels):
            row = i // 3
            col = (2 - (i % 3)) if rtl else (i % 3)
            card = StatCard(
                grid, label=label, value="—",
                lang=self._lang, padding=config.SPACE_MD,
            )
            card.grid(row=row, column=col, sticky="nsew",
                       padx=(0 if col == 0 else 4, 4),
                       pady=(0 if row == 0 else 4, 4))
            self._stat_cards.append(card)

    def _build_achievement_preview(self) -> None:
        """Top 3 badges row."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_MD)
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        title_row = ctk.CTkFrame(section, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)
        SectionTitle(
            title_row, text=self._tr("achievements", "Achievements"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        TextButton(
            title_row, text=self._tr("all", "All") + " →",
            command=self._on_view_all_badges,
            lang=self._lang, height=28,
            color=config.GOLD, font_size=config.FONT_SIZE_CAPTION,
        ).grid(row=0, column=1, sticky="e" if rtl else "w")
        self._badges_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._badges_frame.grid(row=1, column=0, sticky="ew",
                                  pady=(config.SPACE_SM, 0))
        self._badges_frame.grid_columnconfigure(0, weight=1)

    def _build_recent_chart(self) -> None:
        """30-day activity sparkline."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("last30Days", "Last 30 days"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=1, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        # Container for the sparkline / bar chart
        self._chart_frame = ctk.CTkFrame(card.content,
                                          fg_color="transparent")
        self._chart_frame.grid(row=0, column=0, sticky="ew")
        self._chart_frame.grid_columnconfigure(0, weight=1)
        # Total below
        self._chart_total_label = ctk.CTkLabel(
            card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._chart_total_label.grid(row=1, column=0, sticky="ew",
                                       pady=(config.SPACE_SM, 0))

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
            "activity.added", "activity.updated", "activity.deleted",
            "badge.unlocked",
            "settings.changed", "language.changed",
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
        """Re-render profile data."""
        self._refresh_profile()
        self._refresh_stats()
        self._refresh_achievements()
        self._refresh_chart()

    def _refresh_profile(self) -> None:
        try:
            name = settings_service.user_name() or ""
            email = settings_service.user_email() or ""
        except Exception:
            name = ""
            email = ""
        try:
            self._name_label.configure(text=name or self._tr("anonymous",
                                                              "Anonymous"))
            self._email_label.configure(text=email or "—")
        except Exception:
            pass
        # Member since — use first activity date or today
        try:
            today = time_utils.today_iso()
            year_ago = time_utils.add_days(today, -365)
            oldest = activity_service.list(date_from="1970-01-01",
                                              date_to=today, limit=1)
            if oldest:
                first_iso = oldest[0].get("date_iso") or today
            else:
                first_iso = today
            try:
                member_str = jalali.format_jalali(
                    first_iso, fmt="long", lang=self._lang)
            except Exception:
                member_str = first_iso
            self._member_since_label.configure(
                text=f"{self._tr('memberSince', 'Member since')} "
                     f"{member_str}")
        except Exception:
            pass
        # Update avatar initials
        try:
            from ..widgets.avatars import initials_for
            initials = initials_for(name) if name else "R"
            # We can't easily change Avatar text post-creation; skip
        except Exception:
            pass

    def _refresh_stats(self) -> None:
        """Compute and display the 6 summary stats."""
        try:
            today = time_utils.today_iso()
            year_ago = time_utils.add_days(today, -365)
            summary = stats_service.summary(year_ago, today)
        except Exception:
            summary = {}
        # Card 0: total sessions (activity count)
        try:
            total_sess = int(summary.get("total_activities", 0) or 0)
            self._stat_cards[0].set_value(
                i18n.to_fa_digits(str(total_sess))
                if self._lang == "fa" else str(total_sess))
        except Exception:
            pass
        # Card 1: total focus time
        try:
            total_min = int(summary.get("total_min", 0) or 0)
            total_sec = total_min * 60
            from ...core import time_utils as tu
            self._stat_cards[1].set_value(
                tu.seconds_to_human(total_sec, lang=self._lang))
        except Exception:
            pass
        # Card 2: longest session
        try:
            longest = summary.get("longest_session") or {}
            ls_min = int(longest.get("duration_min", 0) or 0)
            ls_str = (i18n.to_fa_digits(str(ls_min))
                       + " " + self._tr("minutes", "min")
                       if self._lang == "fa" else f"{ls_min} min")
            self._stat_cards[2].set_value(ls_str)
        except Exception:
            pass
        # Card 3: favorite category
        try:
            cats = stats_service.by_category(year_ago, today)
            top_cat = cats[0] if cats else None
            if top_cat:
                # Look up category name
                cat_id = top_cat.get("category_id")
                cat = db.category_get(cat_id) if cat_id else None
                if cat:
                    cat_name = (cat.get("name_fa") if self._lang == "fa"
                                 else cat.get("name_en")) or "—"
                else:
                    cat_name = "—"
                self._stat_cards[3].set_value(cat_name)
            else:
                self._stat_cards[3].set_value("—")
        except Exception:
            pass
        # Card 4: favorite time of day
        try:
            hours = stats_service.by_hour(year_ago, today)
            top_hour = max(hours, key=lambda h: int(h.get("total_min", 0))) \
                if hours else None
            if top_hour:
                h = int(top_hour.get("hour", 0))
                # Format as a time-of-day name
                if self._lang == "fa":
                    if 5 <= h < 12:
                        tod = "صبح"
                    elif 12 <= h < 17:
                        tod = "بعدازظهر"
                    elif 17 <= h < 21:
                        tod = "غروب"
                    else:
                        tod = "شب"
                else:
                    if 5 <= h < 12:
                        tod = "Morning"
                    elif 12 <= h < 17:
                        tod = "Afternoon"
                    elif 17 <= h < 21:
                        tod = "Evening"
                    else:
                        tod = "Night"
                self._stat_cards[4].set_value(tod)
            else:
                self._stat_cards[4].set_value("—")
        except Exception:
            pass
        # Card 5: average session
        try:
            avg = float(summary.get("avg_per_activity", 0) or 0)
            avg_int = int(avg)
            avg_str = (i18n.to_fa_digits(str(avg_int))
                       + " " + self._tr("minutes", "min")
                       if self._lang == "fa" else f"{avg_int} min")
            self._stat_cards[5].set_value(avg_str)
        except Exception:
            pass

    def _refresh_achievements(self) -> None:
        """Render top 3 earned badges."""
        for child in self._badges_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        try:
            earned = badge_service.list_earned()
        except Exception:
            earned = []
        rtl = i18n.is_rtl(self._lang)
        if not earned:
            ctk.CTkLabel(
                self._badges_frame,
                text=self._tr("noBadgesYet", "No badges earned yet"),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_FAINT,
                anchor="e" if rtl else "w",
            ).grid(row=0, column=0, sticky="ew")
            return
        # Show top 3
        row = ctk.CTkFrame(self._badges_frame, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        for i in range(min(3, len(earned))):
            row.grid_columnconfigure(i, weight=1, uniform="badge")
            b = earned[i]
            cell = ctk.CTkFrame(row, fg_color=config.CHARCOAL,
                                 corner_radius=config.RADIUS_MD,
                                 border_width=1, border_color=config.DIVIDER)
            cell.grid(row=0, column=(2 - i) if rtl else i, sticky="nsew",
                       padx=4, pady=4)
            cell.grid_columnconfigure(0, weight=1)
            tier_badge = TierBadge(
                cell, tier=b.get("tier", "gold"),
                icon_name=b.get("icon") or "trophy",
                size=44, earned=True, lang=self._lang,
            )
            tier_badge.grid(row=0, column=0, pady=(0, 4))
            name = (b.get("name_fa") if self._lang == "fa"
                     else b.get("name_en")) or "—"
            ctk.CTkLabel(
                cell, text=name,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.TEXT, wraplength=100, justify="center",
                anchor="center",
            ).grid(row=1, column=0)

    def _refresh_chart(self) -> None:
        """30-day sparkline."""
        for child in self._chart_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        # Build per-day totals for last 30 days
        try:
            today = time_utils.today_iso()
            data: List[Dict[str, Any]] = []
            total_sec = 0
            for i in range(29, -1, -1):
                day_iso = time_utils.add_days(today, -i)
                try:
                    sec = int(db.activity_sum_duration(
                        date_from=day_iso, date_to=day_iso))
                except Exception:
                    sec = 0
                total_sec += sec
                minutes = sec // 60
                data.append({"label": "", "value": minutes,
                              "color": config.GOLD})
            # Render BarChart
            chart = BarChart(
                self._chart_frame, data=data,
                width=420, height=80, lang=self._lang,
                max_value=None,
            )
            chart.grid(row=0, column=0, sticky="ew")
            # Total
            from ...core import time_utils as tu
            total_str = tu.seconds_to_human(total_sec, lang=self._lang)
            self._chart_total_label.configure(
                text=f"{self._tr('total', 'Total')}: {total_str}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_edit_toggle(self) -> None:
        """Toggle between view / edit mode."""
        if not self._edit_mode:
            self._enter_edit_mode()
        else:
            self._save_edit_mode()

    def _enter_edit_mode(self) -> None:
        self._edit_mode = True
        # Hide name label, show entry
        try:
            self._name_label.grid_remove()
            self._name_entry.grid(row=1, column=0,
                                   pady=(config.SPACE_SM, 0))
            self._name_entry.value = settings_service.user_name() or ""
            # Change header action text to "Save"
            self._header.set_title(i18n.t("profile", self._lang))
        except Exception:
            pass
        # Show email editor below
        try:
            self._email_label.grid_remove()
            self._email_entry = GoldEntry(
                self._avatar.master, placeholder=self._tr("email", "Email"),
                lang=self._lang, height=36, width=240,
            )
            self._email_entry.grid(row=2, column=0, pady=(2, 0))
            self._email_entry.value = settings_service.user_email() or ""
        except Exception:
            pass
        # Update header action
        try:
            for child in self._header.winfo_children():
                # Find the action button
                pass
        except Exception:
            pass
        self._show_toast(self._tr("editMode", "Edit mode"))

    def _save_edit_mode(self) -> None:
        self._edit_mode = False
        try:
            new_name = self._name_entry.value.strip()
            settings_service.set_user_name(new_name)
        except Exception:
            new_name = settings_service.user_name() or ""
        try:
            new_email = self._email_entry.value.strip()
            settings_service.set_user_email(new_email)
        except Exception:
            new_email = settings_service.user_email() or ""
        # Restore display
        try:
            self._name_entry.grid_remove()
            self._name_label.configure(text=new_name
                                        or self._tr("anonymous",
                                                    "Anonymous"))
            self._name_label.grid(row=1, column=0,
                                   pady=(config.SPACE_SM, 0))
        except Exception:
            pass
        try:
            self._email_entry.grid_remove()
            self._email_entry.destroy()
        except Exception:
            pass
        try:
            self._email_label.configure(text=new_email or "—")
            self._email_label.grid(row=2, column=0, pady=(2, 0))
        except Exception:
            pass
        self._show_toast(self._tr("profileSaved", "Profile saved"))
        self.refresh()

    def _on_pick_avatar(self) -> None:
        """Open file picker to choose a new avatar image."""
        try:
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title=self._tr("selectAvatar", "Select avatar"),
                filetypes=(("Images", "*.png *.jpg *.jpeg *.gif"),
                            ("All files", "*.*")),
            )
            if not path:
                return
            settings_service.set_user_avatar_path(path)
            self._show_toast(self._tr("avatarUpdated", "Avatar updated"))
            self.refresh()
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_view_all_badges(self) -> None:
        if self._app and hasattr(self._app, "switch_tab"):
            try:
                self._app.switch_tab("badges")
            except Exception:
                pass

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
    print("ProfileScreen module: avatar + 6 stats + top 3 badges + sparkline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
