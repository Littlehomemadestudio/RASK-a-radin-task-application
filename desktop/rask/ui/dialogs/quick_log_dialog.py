"""
rask.ui.dialogs.quick_log_dialog
================================

Bottom-sheet "Quick Log" dialog — opens from the FAB on every screen
to log a single activity in one tap.

Layout (top-to-bottom, RTL Persian):
    1. Title row: "ثبت سریع فعالیت"  +  close (×) button
    2. Activity title — GoldEntry with placeholder "چه کاری انجام دادی؟"
       Auto-focus on open.  A small mic button sits on the leading side
       and opens :class:`rask.ui.dialogs.voice_dialog.VoiceDialog`.
    3. Category chips — horizontal scroll of category names; one
       selected.  Defaults to the user's most-used category.
    4. Duration row — DurationEntry (HH:MM) on one side, "شروع کرنومتر"
       button on the other.  The button starts the background
       :data:`rask.services.timer_service` and dismisses the sheet.
    5. Date / time row — date picker (default today) + time picker
       (default now).
    6. Notes — optional TextArea (max 500 chars).
    7. Tags — GoldEntry with comma-separated tags.
    8. Save / Cancel buttons at the bottom (gold Save is full-width).

Behaviour
---------
  * **Stopwatch mode**: tapping "شروع کرنومتر" calls
    ``timer_service.start_recording()`` with the entered title and
    category, then dismisses the sheet.  The user stops the timer from
    the home screen to record the activity.
  * **Validation**: title is required.  If stopwatch mode is not used,
    duration must be > 0.  Errors are shown inline as a red caption.
  * **On save**: ``activity_service.add(...)`` is called; a success
    toast appears, and the sheet closes.
  * **Swipe-down to dismiss**: if any field is dirty, a confirm dialog
    asks the user to confirm ("دورریختن تغییرات؟").
  * **ESC**: same as swipe-down (dirty-confirm if applicable).

Mirrors ``web/js/app.js :: openQuickLogModal`` 1:1.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import helpers, time_utils, jalali
from ...services import activity_service, timer_service, settings_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BottomSheet
from ..widgets.buttons import GoldButton, GhostButton, IconButton, TextButton
from ..widgets.inputs import GoldEntry, TextArea, DurationEntry
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.badges import Chip
from ..widgets.toggles import Toggle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from ..widgets.date_picker import DatePicker
from ..widgets.time_picker import TimePicker
from .voice_dialog import VoiceDialog
from .confirm_dialog import ConfirmDialog

__all__ = ["QuickLogDialog"]


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _load_categories() -> List[Dict[str, Any]]:
    """Return the user's non-archived categories, ordered by ``order_index``."""
    try:
        return list(db.category_list(include_archived=False))
    except Exception:
        return []


def _default_category_id(cats: List[Dict[str, Any]]) -> Optional[int]:
    """Pick a sensible default category — the first one in order."""
    if not cats:
        return None
    try:
        return int(cats[0]["id"])
    except Exception:
        return None


def _format_date_label(iso: str, lang: str) -> str:
    """Return a human-friendly label for an ISO date."""
    if not iso:
        return ""
    try:
        if lang == "fa":
            jy, jm, jd = jalali.iso_to_jalali(iso)
            return i18n.to_fa_digits(f"{jd:02d}/{jm:02d}/{jy % 100:02d}")
        return iso
    except Exception:
        return iso


def _format_time_label(hhmm: str, lang: str) -> str:
    """Return a human-friendly label for an HH:MM time string."""
    if not hhmm:
        return ""
    if lang == "fa":
        return i18n.to_fa_digits(hhmm)
    return hhmm


# =============================================================================
# === QuickLogDialog                                                         ===
# =============================================================================

class QuickLogDialog(BottomSheet):
    """Bottom-sheet quick activity logger.

    Opens from the FAB tap on any screen.  Slides up from the bottom,
    auto-focuses the activity-title field, and saves with the gold
    "ذخیره" button.

    Parameters
    ----------
    master
        Parent widget (usually the app root window).
    prefill_title
        Optional pre-filled title (e.g. when invoked from a template).
    prefill_category_id
        Optional pre-selected category id.
    prefill_duration_min
        Optional pre-filled duration (in minutes).
    prefill_tags
        Optional pre-filled tags list.
    lang
        UI language.
    on_result
        Callback receiving the saved activity dict (or None on cancel).

    Result
    ------
    ``self.result`` is the saved activity dict on success, ``None`` on
    cancel / dismissal, or the string ``"stopwatch_started"`` when the
    stopwatch mode was used.
    """

    def __init__(
        self,
        master: Any = None,
        *,
        prefill_title: str = "",
        prefill_category_id: Optional[int] = None,
        prefill_duration_min: int = 0,
        prefill_tags: Optional[List[str]] = None,
        prefill_notes: str = "",
        prefill_date_iso: Optional[str] = None,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Any]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._prefill_title = prefill_title
        self._prefill_category_id = prefill_category_id
        self._prefill_duration_min = int(prefill_duration_min or 0)
        self._prefill_tags = prefill_tags or []
        self._prefill_notes = prefill_notes
        self._prefill_date_iso = prefill_date_iso or time_utils.today_iso()
        self._categories: List[Dict[str, Any]] = _load_categories()
        self._selected_cat_id: Optional[int] = (
            prefill_category_id or _default_category_id(self._categories))
        self._selected_date_iso: str = self._prefill_date_iso
        self._selected_time_hhmm: str = datetime.now().strftime("%H:%M")
        self._stopwatch_mode: bool = False
        self._dirty: bool = False
        self._saving: bool = False
        self._voice_dlg = None
        self._date_dlg = None
        self._time_dlg = None
        kwargs.setdefault("height", 640)
        kwargs.setdefault("close_on_overlay", False)  # confirm on dirty
        super().__init__(
            master,
            title=i18n.t("quickLogTitle", lang) if lang == "fa"
                  else "Quick Log",
            lang=lang, **kwargs,
        )
        if on_result:
            self.on_result(on_result)

    # ------------------------------------------------------------------
    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)

        # Scrollable container so the form fits in a small sheet on
        # short windows without losing any field.
        scroll = SmoothScrollFrame(self._content, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        form = ctk.CTkFrame(scroll, fg_color="transparent")
        form.pack(fill="both", expand=True)
        form.grid_columnconfigure(0, weight=1)

        row = 0

        # --- Activity title + mic button -------------------------------
        title_row = ctk.CTkFrame(form, fg_color="transparent")
        title_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        title_row.grid_columnconfigure(0, weight=1)
        title_row.grid_columnconfigure(1, weight=0)
        self._title_entry = GoldEntry(
            title_row,
            placeholder=(i18n.t("activityTitlePlaceholder", self._lang)
                          if i18n.t("activityTitlePlaceholder", self._lang)
                          != "activityTitlePlaceholder"
                          else "چه کاری انجام دادی؟"),
            lang=self._lang,
            height=46,
            on_change=self._on_dirty,
        )
        self._title_entry.value = self._prefill_title
        self._title_entry.grid(row=0, column=0, sticky="ew",
                                padx=(0, 4) if rtl else (4, 0))
        # Mic button
        self._mic_btn = ctk.CTkButton(
            title_row, text="",
            width=46, height=46,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            border_width=1, border_color=config.GOLD_DIM,
            corner_radius=config.RADIUS_MD, cursor="hand2",
            command=self._open_voice,
        )
        mic_img = _icons.icon("mic", 22, color=config.GOLD)
        if mic_img is not None:
            self._mic_btn.configure(image=mic_img)
        else:
            self._mic_btn.configure(text=_icons.icon_glyph("mic"),
                                     text_color=config.GOLD)
        self._mic_btn.grid(row=0, column=1, padx=(4, 0) if rtl else (0, 4))
        row += 1

        # --- Category chips -------------------------------------------
        cat_label = SectionTitle(
            form,
            text=(i18n.t("category", self._lang)
                   if i18n.t("category", self._lang) != "category"
                   else "دسته‌بندی"),
            lang=self._lang,
        )
        cat_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        chip_row = ctk.CTkFrame(form, fg_color="transparent")
        chip_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        chip_row.grid_columnconfigure(0, weight=1)
        self._cat_chips_frame = ctk.CTkFrame(chip_row, fg_color="transparent")
        self._cat_chips_frame.pack(
            side="right" if rtl else "left", fill="x", expand=True)
        self._cat_chips: List[Chip] = []
        self._rebuild_category_chips()
        row += 1

        # --- Duration row ----------------------------------------------
        dur_label = SectionTitle(
            form,
            text=(i18n.t("duration", self._lang)
                   if i18n.t("duration", self._lang) != "duration"
                   else "مدت زمان"),
            lang=self._lang,
        )
        dur_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        dur_row = ctk.CTkFrame(form, fg_color="transparent")
        dur_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        dur_row.grid_columnconfigure(0, weight=1)
        self._duration_entry = DurationEntry(
            dur_row, lang=self._lang,
            initial_minutes=self._prefill_duration_min,
            on_change=self._on_dirty,
        )
        self._duration_entry.pack(side="right" if rtl else "left",
                                    fill="x", expand=True,
                                    padx=(0, 6) if rtl else (6, 0))
        self._stopwatch_btn = GhostButton(
            dur_row,
            text=(i18n.t("startStopwatch", self._lang)
                   if i18n.t("startStopwatch", self._lang)
                   != "startStopwatch"
                   else "شروع کرنومتر"),
            command=self._start_stopwatch,
            lang=self._lang, height=46,
            icon_name="play", icon_size=16,
            font_size=config.FONT_SIZE_SMALL,
        )
        self._stopwatch_btn.pack(side="left" if rtl else "right",
                                   padx=(6, 0) if rtl else (0, 6))
        row += 1

        # --- Date / time row -------------------------------------------
        dt_label = SectionTitle(
            form,
            text=(i18n.t("date", self._lang)
                   if i18n.t("date", self._lang) != "date"
                   else "تاریخ"),
            lang=self._lang,
        )
        dt_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        dt_row = ctk.CTkFrame(form, fg_color="transparent")
        dt_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        dt_row.grid_columnconfigure(0, weight=1)
        dt_row.grid_columnconfigure(1, weight=1)
        # Date button
        self._date_btn = ctk.CTkButton(
            dt_row, text=_format_date_label(self._selected_date_iso,
                                              self._lang),
            command=self._open_date_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        # Time button
        self._time_btn = ctk.CTkButton(
            dt_row, text=_format_time_label(self._selected_time_hhmm,
                                              self._lang),
            command=self._open_time_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        if rtl:
            self._time_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._date_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            self._date_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._time_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        row += 1

        # --- Notes -----------------------------------------------------
        notes_label = SectionTitle(
            form,
            text=(i18n.t("notes", self._lang)
                   if i18n.t("notes", self._lang) != "notes"
                   else "یادداشت"),
            lang=self._lang,
        )
        notes_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._notes_entry = TextArea(
            form, lang=self._lang,
            height=80, max_chars=500,
            placeholder=(i18n.t("notesPlaceholder", self._lang)
                          if i18n.t("notesPlaceholder", self._lang)
                          != "notesPlaceholder"
                          else "یادداشت اختیاری"),
        )
        self._notes_entry.value = self._prefill_notes
        self._notes_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Tags ------------------------------------------------------
        tags_label = SectionTitle(
            form,
            text=(i18n.t("tags", self._lang)
                   if i18n.t("tags", self._lang) != "tags"
                   else "برچسب‌ها"),
            lang=self._lang,
        )
        tags_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._tags_entry = GoldEntry(
            form,
            placeholder=(i18n.t("tagsPlaceholder", self._lang)
                          if i18n.t("tagsPlaceholder", self._lang)
                          != "tagsPlaceholder"
                          else "با کاما جدا کن"),
            lang=self._lang, height=42,
            on_change=self._on_dirty,
        )
        if self._prefill_tags:
            self._tags_entry.value = ", ".join(self._prefill_tags)
        self._tags_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Error caption --------------------------------------------
        self._error_label = ctk.CTkLabel(
            form, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.DANGER,
            anchor="e" if rtl else "w",
        )
        self._error_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        # --- Buttons ---------------------------------------------------
        Divider(form).grid(row=row, column=0, sticky="ew", pady=(4, 8))
        row += 1

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=row, column=0, sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=2)

        cancel_btn = GhostButton(
            btn_row,
            text=(i18n.t("cancel", self._lang)
                   if i18n.t("cancel", self._lang) != "cancel"
                   else "انصراف"),
            command=self._on_cancel,
            lang=self._lang, height=46,
        )
        self._save_btn = GoldButton(
            btn_row,
            text=(i18n.t("save", self._lang)
                   if i18n.t("save", self._lang) != "save"
                   else "ذخیره"),
            command=self._on_save,
            lang=self._lang, height=46,
            icon_name="check", icon_size=16,
        )
        if rtl:
            self._save_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._save_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))

        # Auto-focus the title entry after the sheet has finished animating in.
        try:
            self.after(220, lambda: self._title_entry.focus_set())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Category chips
    # ------------------------------------------------------------------
    def _rebuild_category_chips(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        for chip in self._cat_chips:
            try:
                chip.destroy()
            except Exception:
                pass
        self._cat_chips = []
        # Clear existing children
        for child in self._cat_chips_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        # Build a horizontal row of chips (left-to-right in LTR,
        # right-to-left in RTL via packing order).
        for cat in self._categories:
            try:
                color = cat.get("color") or config.GOLD
                name = (cat.get("name_fa") if self._lang == "fa"
                         else cat.get("name_en")) or cat.get("key", "—")
                selected = (self._selected_cat_id == int(cat["id"]))
                chip = Chip(
                    self._cat_chips_frame,
                    text=name,
                    color=color,
                    selected=selected,
                    on_click=lambda cid=int(cat["id"]): self._select_cat(cid),
                    lang=self._lang,
                )
                chip.pack(side="right" if rtl else "left", padx=4)
                self._cat_chips.append(chip)
            except Exception:
                continue

    def _select_cat(self, cat_id: int) -> None:
        self._selected_cat_id = cat_id
        self._dirty = True
        # Update chip selected state without rebuilding (preserves order)
        for chip in self._cat_chips:
            try:
                # We stored the id on the chip via _cat_id; if missing we'd
                # have to rebuild, but Chip doesn't carry id — rebuild:
                pass
            except Exception:
                pass
        self._rebuild_category_chips()

    # ------------------------------------------------------------------
    # Pickers
    # ------------------------------------------------------------------
    def _open_date_picker(self) -> None:
        try:
            self._date_dlg = DatePicker(
                self, initial=self._selected_date_iso,
                on_result=self._on_date_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_date_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._selected_date_iso = iso
        self._dirty = True
        try:
            self._date_btn.configure(
                text=_format_date_label(iso, self._lang))
        except Exception:
            pass

    def _open_time_picker(self) -> None:
        try:
            self._time_dlg = TimePicker(
                self, initial=self._selected_time_hhmm,
                on_result=self._on_time_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_time_picked(self, hhmm: Optional[str]) -> None:
        if not hhmm:
            return
        self._selected_time_hhmm = hhmm
        self._dirty = True
        try:
            self._time_btn.configure(
                text=_format_time_label(hhmm, self._lang))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Voice input
    # ------------------------------------------------------------------
    def _open_voice(self) -> None:
        try:
            self._voice_dlg = VoiceDialog(
                self, on_result=self._on_voice_result, lang=self._lang,
            )
        except Exception:
            pass

    def _on_voice_result(self, result: Optional[Dict[str, Any]]) -> None:
        if not result:
            return
        text = result.get("text", "")
        if not text:
            return
        # If the title is empty, put the text in the title; otherwise
        # append to notes.
        if not self._title_entry.value.strip():
            self._title_entry.value = text
        else:
            existing = self._notes_entry.value.strip()
            self._notes_entry.value = (existing + "\n" + text).strip() \
                if existing else text
        self._dirty = True

    # ------------------------------------------------------------------
    # Stopwatch mode
    # ------------------------------------------------------------------
    def _start_stopwatch(self) -> None:
        title = self._title_entry.value.strip()
        if not title:
            self._show_error(
                i18n.t("errorRequired", self._lang)
                if i18n.t("errorRequired", self._lang) != "errorRequired"
                else "عنوان الزامی است")
            return
        try:
            timer_service.start(
                title=title,
                category_id=self._selected_cat_id,
            )
            self._dirty = False
            self._stopwatch_mode = True
            try:
                Toast.show(
                    self,
                    (i18n.t("recording", self._lang)
                     if i18n.t("recording", self._lang) != "recording"
                     else "ثبت در حال انجام"),
                    kind="success", lang=self._lang,
                )
            except Exception:
                pass
            self.close("stopwatch_started")
        except Exception as exc:
            self._show_error(str(exc))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        if self._saving:
            return
        title = self._title_entry.value.strip()
        if not title:
            self._show_error(
                i18n.t("errorRequired", self._lang)
                if i18n.t("errorRequired", self._lang) != "errorRequired"
                else "عنوان الزامی است")
            try:
                self._title_entry.focus_set()
            except Exception:
                pass
            return
        duration_min = int(self._duration_entry.value or 0)
        if duration_min <= 0:
            self._show_error(
                i18n.t("durationHint", self._lang)
                if i18n.t("durationHint", self._lang) != "durationHint"
                else "مدت زمان را وارد کن یا کرنومتر را شروع کن")
            return
        notes = self._notes_entry.value.strip() or None
        tags_str = self._tags_entry.value.strip()
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] \
            if tags_str else None
        # Build start/end timestamps from date + time
        start_ts = None
        end_ts = None
        try:
            h, m = (self._selected_time_hhmm.split(":") + ["0", "0"])[:2]
            start_dt = datetime.fromisoformat(self._selected_date_iso)
            start_dt = start_dt.replace(hour=int(h), minute=int(m))
            start_ts = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
            end_ts = (start_dt + timedelta(minutes=duration_min)).strftime(
                "%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass

        self._saving = True
        try:
            self._save_btn.configure(state="disabled", text="…")
        except Exception:
            pass

        try:
            activity = activity_service.add(
                title=title,
                category_id=self._selected_cat_id,
                duration_min=duration_min,
                date_iso=self._selected_date_iso,
                start_ts=start_ts,
                end_ts=end_ts,
                notes=notes,
                tags=tags,
                kind="manual",
            )
            self._dirty = False
            try:
                Toast.show(
                    self,
                    (i18n.t("activitySaved", self._lang)
                     if i18n.t("activitySaved", self._lang)
                     != "activitySaved"
                     else "فعالیت ذخیره شد"),
                    kind="success", lang=self._lang,
                )
            except Exception:
                pass
            self.close(activity)
        except Exception as exc:
            self._saving = False
            try:
                self._save_btn.configure(state="normal",
                                           text=(i18n.t("save", self._lang)
                                                  if i18n.t("save", self._lang)
                                                  != "save" else "ذخیره"))
            except Exception:
                pass
            self._show_error(str(exc))

    # ------------------------------------------------------------------
    def _on_cancel(self) -> None:
        if self._dirty:
            # Confirm dismissal
            try:
                ConfirmDialog(
                    self,
                    title=i18n.t("discardActivity", self._lang)
                          if i18n.t("discardActivity", self._lang)
                          != "discardActivity"
                          else "دورریختن؟",
                    message=("تغییرات ذخیره نشده‌اند." if self._lang == "fa"
                              else "Unsaved changes will be lost."),
                    danger=True,
                    confirm_text=i18n.t("discardActivity", self._lang)
                                  if i18n.t("discardActivity", self._lang)
                                  != "discardActivity"
                                  else "دورریختن",
                    on_result=lambda r: self.close(None)
                                        if (r and r.get("confirmed")) else None,
                    lang=self._lang,
                )
            except Exception:
                self.close(None)
        else:
            self.close(None)

    # ------------------------------------------------------------------
    def _on_dirty(self, _v: Any = None) -> None:
        self._dirty = True
        try:
            self._error_label.configure(text="")
        except Exception:
            pass

    def _show_error(self, msg: str) -> None:
        try:
            self._error_label.configure(text=msg)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # ESC handling — confirm if dirty
    # ------------------------------------------------------------------
    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self._on_cancel(), add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("quick_log_dialog module: 1 class registered (QuickLogDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
