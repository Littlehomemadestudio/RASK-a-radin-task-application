"""
rask.ui.dialogs.template_dialog
===============================

Modal dialog for creating / editing a quick-log template.

Layout
------
  * Title row: ``"قالب جدید"`` / ``"ویرایش قالب"``  +  close (×)
  * Template name (GoldEntry, required)
  * Activity title (GoldEntry, required — used as activity title when applied)
  * Default category (PickerSheet)
  * Default duration (DurationEntry, optional)
  * Default tags (GoldEntry, comma-separated)
  * Default notes (TextArea)
  * Shortcut key (GoldEntry, single key, optional)
  * Icon picker grid (ring, book, briefcase, heart, palette, users,
    moon, star, spark, flame, etc.)
  * Color picker (gold palette)
  * Save / Cancel buttons
  * Delete (when editing)

Mirrors ``web/js/app.js :: openTemplateDialog`` 1:1.
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
from ...core import helpers
from ...services import template_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.inputs import GoldEntry, TextArea, DurationEntry
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from ..widgets.sheets import PickerSheet
from .confirm_dialog import ConfirmDialog
from .goal_dialog import _ColorSwatchGrid, GOLD_PALETTE

__all__ = ["TemplateDialog"]


# =============================================================================
# === Icon picker grid                                                      ===
# =============================================================================

# The set of icons a user can pick for a template.  These mirror the
# icon names available in :mod:`rask.ui.widgets.icons` and the default
# categories in :data:`rask.config.DEFAULT_CATEGORIES`.
TEMPLATE_ICONS: List[str] = [
    "ring", "book", "briefcase", "heart", "palette",
    "users", "moon", "star", "spark", "flame",
    "trophy", "bolt", "medal", "diamond", "sun",
    "sunrise", "music", "camera", "leaf", "clock",
    "calendar", "bell", "tag", "shield", "bolt",
]


class _IconPickerGrid(ctk.CTkFrame):
    """Grid of icon buttons — click to select one."""

    def __init__(
        self,
        master: Any,
        icons: List[str],
        selected: Optional[str] = None,
        on_change: Optional[Callable[[str], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._icons = list(icons)
        self._selected = selected
        self._on_change = on_change
        self._buttons: List[ctk.CTkButton] = []
        cols = 5
        for i in range(cols):
            self.grid_columnconfigure(i, weight=1)
        for i, icon_name in enumerate(self._icons):
            r, c = divmod(i, cols)
            is_sel = (icon_name == selected)
            btn = ctk.CTkButton(
                self, text="",
                width=44, height=44,
                fg_color=config.GOLD if is_sel else config.SURFACE,
                hover_color=config.GOLD_BRIGHT if is_sel
                              else config.SURFACE_HI,
                border_width=2,
                border_color=config.GOLD if is_sel else config.SURFACE_HI,
                corner_radius=config.RADIUS_MD, cursor="hand2",
                command=lambda n=icon_name: self._select(n),
            )
            # Icon
            color = config.MATTE_BLACK if is_sel else config.GOLD
            img = _icons.icon(icon_name, 22, color=color)
            if img is not None:
                btn.configure(image=img)
            else:
                btn.configure(text=_icons.icon_glyph(icon_name),
                                text_color=color)
            btn.grid(row=r, column=c, padx=4, pady=4)
            self._buttons.append(btn)

    def _select(self, icon_name: str) -> None:
        self._selected = icon_name
        for btn, name in zip(self._buttons, self._icons):
            is_sel = (name == icon_name)
            try:
                btn.configure(
                    fg_color=config.GOLD if is_sel else config.SURFACE,
                    border_color=config.GOLD if is_sel else config.SURFACE_HI,
                )
                color = config.MATTE_BLACK if is_sel else config.GOLD
                img = _icons.icon(name, 22, color=color)
                if img is not None:
                    btn.configure(image=img, text="")
                else:
                    btn.configure(text=_icons.icon_glyph(name),
                                   text_color=color, image="")
            except Exception:
                pass
        if self._on_change:
            try:
                self._on_change(icon_name)
            except Exception:
                pass

    @property
    def value(self) -> Optional[str]:
        return self._selected


# =============================================================================
# === TemplateDialog                                                         ===
# =============================================================================

class TemplateDialog(BaseDialog):
    """Modal create / edit template dialog.

    Parameters
    ----------
    master
        Parent widget.
    template_id
        Optional template id to edit.  ``None`` creates a new template.
    lang
        UI language.
    on_result
        Callback receiving ``{"action": str, "template": dict}``.
    """

    def __init__(
        self,
        master: Any,
        template_id: Optional[int] = None,
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._template_id = template_id
        self._template: Optional[Dict[str, Any]] = None
        if template_id is not None:
            try:
                self._template = template_service.get(template_id)
            except Exception:
                self._template = None
        if self._template:
            self._name = self._template.get("name", "")
            self._title_text = self._template.get("title", "")
            self._category_id = self._template.get("category_id")
            self._duration_min = int(self._template.get("duration_min") or 0)
            self._tags = list(self._template.get("tags") or [])
            self._notes = self._template.get("notes") or ""
            self._shortcut = self._template.get("shortcut") or ""
            self._icon = self._template.get("icon") or "ring"
            self._color = self._template.get("color") or config.GOLD
        else:
            self._name = ""
            self._title_text = ""
            self._category_id = None
            self._duration_min = 0
            self._tags = []
            self._notes = ""
            self._shortcut = ""
            self._icon = "ring"
            self._color = config.GOLD
        self._dirty = False
        self._saving = False
        self._cat_dlg = None
        kwargs.setdefault("height", 720)
        kwargs.setdefault("width", 480)
        kwargs.setdefault("close_on_overlay", False)
        title = (i18n.t("editTemplate", lang) if self._template
                  else i18n.t("newTemplate", lang))
        super().__init__(master, title=title, lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    # ------------------------------------------------------------------
    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        scroll = SmoothScrollFrame(self._content, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        form = ctk.CTkFrame(scroll, fg_color="transparent")
        form.pack(fill="both", expand=True)
        form.grid_columnconfigure(0, weight=1)

        row = 0

        # --- Template name ------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("templateName", self._lang)
                   if i18n.t("templateName", self._lang)
                   != "templateName"
                   else "نام قالب"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._name_entry = GoldEntry(
            form, lang=self._lang, height=46,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._name_entry.value = self._name
        self._name_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Activity title -----------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("activityTitle", self._lang)
                   if i18n.t("activityTitle", self._lang)
                   != "activityTitle"
                   else "عنوان فعالیت"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._title_entry = GoldEntry(
            form, lang=self._lang, height=46,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._title_entry.value = self._title_text
        self._title_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Category picker ----------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("templateCategory", self._lang)
                   if i18n.t("templateCategory", self._lang)
                   != "templateCategory"
                   else "دسته پیش‌فرض"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._cat_btn = ctk.CTkButton(
            form, text=self._category_label(),
            command=self._open_category_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._cat_btn.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Default duration ---------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("templateDuration", self._lang)
                   if i18n.t("templateDuration", self._lang)
                   != "templateDuration"
                   else "مدت پیش‌فرض"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._duration_entry = DurationEntry(
            form, lang=self._lang,
            initial_minutes=self._duration_min,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._duration_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Default tags -------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("templateTags", self._lang)
                   if i18n.t("templateTags", self._lang)
                   != "templateTags"
                   else "برچسب‌های پیش‌فرض"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._tags_entry = GoldEntry(
            form, lang=self._lang, height=42,
            on_change=lambda _v: self._mark_dirty(),
        )
        if self._tags:
            self._tags_entry.value = ", ".join(self._tags)
        self._tags_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Default notes ------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("templateNotes", self._lang)
                   if i18n.t("templateNotes", self._lang)
                   != "templateNotes"
                   else "یادداشت پیش‌فرض"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._notes_entry = TextArea(
            form, lang=self._lang, height=80, max_chars=500,
        )
        self._notes_entry.value = self._notes
        self._notes_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Shortcut key -------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("templateShortcut", self._lang)
                   if i18n.t("templateShortcut", self._lang)
                   != "templateShortcut"
                   else "کلید میانبر"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        shortcut_row = ctk.CTkFrame(form, fg_color="transparent")
        shortcut_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        shortcut_row.grid_columnconfigure(0, weight=1)
        self._shortcut_entry = GoldEntry(
            shortcut_row, lang=self._lang, height=42,
            max_chars=3,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._shortcut_entry.value = self._shortcut
        self._shortcut_entry.pack(side="right" if rtl else "left",
                                    fill="x", expand=True)
        ctk.CTkLabel(
            shortcut_row,
            text=("حداکثر ۳ نویسه" if self._lang == "fa"
                   else "Max 3 chars"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
        ).pack(side="left" if rtl else "right", padx=8)
        row += 1

        # --- Icon picker --------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("categoryIcon", self._lang)
                   if i18n.t("categoryIcon", self._lang)
                   != "categoryIcon"
                   else "آیکن"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._icon_grid = _IconPickerGrid(
            form, icons=TEMPLATE_ICONS,
            selected=self._icon,
            on_change=lambda n: self._on_icon_change(n),
        )
        self._icon_grid.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Color picker -------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("categoryColor", self._lang)
                   if i18n.t("categoryColor", self._lang)
                   != "categoryColor"
                   else "رنگ"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._color_grid = _ColorSwatchGrid(
            form, colors=GOLD_PALETTE, selected=self._color,
            on_change=lambda col: self._on_color_change(col),
        )
        self._color_grid.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Error caption ------------------------------------------
        self._error_label = ctk.CTkLabel(
            form, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.DANGER,
            anchor="e" if rtl else "w",
        )
        self._error_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        Divider(form).grid(row=row, column=0, sticky="ew", pady=(4, 8))
        row += 1

        # --- Delete (if editing) ------------------------------------
        if self._template:
            delete_btn = TextButton(
                form,
                text=(i18n.t("delete", self._lang)
                       if i18n.t("delete", self._lang) != "delete"
                       else "حذف"),
                command=self._on_delete,
                lang=self._lang, height=38,
                color=config.DANGER, hover_color=config.DANGER_DIM,
                icon_name="delete", icon_size=14,
            )
            delete_btn.pack(fill="x", pady=(0, 6))

        # --- Buttons ------------------------------------------------
        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x")
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
                   if i18n.t("save", self._lang) != "save" else "ذخیره"),
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

    # ------------------------------------------------------------------
    def _category_label(self) -> str:
        if not self._category_id:
            return (i18n.t("allCategories", self._lang)
                     if i18n.t("allCategories", self._lang)
                     != "allCategories"
                     else "همه دسته‌ها")
        try:
            cat = db.category_get(int(self._category_id))
            if cat:
                return (cat.get("name_fa") if self._lang == "fa"
                         else cat.get("name_en")) or cat.get("key", "—")
        except Exception:
            pass
        return "—"

    def _open_category_picker(self) -> None:
        try:
            cats = db.category_list(include_archived=False)
        except Exception:
            cats = []
        options: List[str] = [
            (i18n.t("allCategories", self._lang)
              if i18n.t("allCategories", self._lang)
              != "allCategories"
              else "همه دسته‌ها"),
        ]
        cat_ids: List[Optional[int]] = [None]
        for c in cats:
            name = (c.get("name_fa") if self._lang == "fa"
                     else c.get("name_en")) or c.get("key", "—")
            options.append(name)
            cat_ids.append(int(c["id"]))
        try:
            self._cat_dlg = PickerSheet(
                self,
                title=(i18n.t("templateCategory", self._lang)
                        if i18n.t("templateCategory", self._lang)
                        != "templateCategory"
                        else "دسته"),
                options=options,
                selected=self._category_label(),
                on_result=lambda label: self._on_category_picked(label,
                                                                   cat_ids,
                                                                   options),
                lang=self._lang,
            )
        except Exception:
            pass

    def _on_category_picked(
        self,
        label: Optional[str],
        cat_ids: List[Optional[int]],
        options: List[str],
    ) -> None:
        if not label:
            return
        try:
            idx = options.index(label)
            self._category_id = cat_ids[idx]
        except (ValueError, IndexError):
            self._category_id = None
        self._dirty = True
        try:
            self._cat_btn.configure(text=self._category_label())
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_icon_change(self, name: str) -> None:
        self._icon = name
        self._dirty = True

    def _on_color_change(self, color: str) -> None:
        self._color = color
        self._dirty = True

    # ------------------------------------------------------------------
    def _mark_dirty(self, _v: Any = None) -> None:
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
    def _on_save(self) -> None:
        if self._saving:
            return
        name = self._name_entry.value.strip()
        if not name:
            self._show_error(
                "نام قالب الزامی است" if self._lang == "fa"
                else "Template name is required")
            return
        title = self._title_entry.value.strip()
        if not title:
            self._show_error(
                "عنوان فعالیت الزامی است" if self._lang == "fa"
                else "Activity title is required")
            return
        duration_min = int(self._duration_entry.value or 0)
        tags_str = self._tags_entry.value.strip()
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] \
            if tags_str else None
        notes = self._notes_entry.value.strip() or None
        shortcut = self._shortcut_entry.value.strip()[:3] or None
        self._saving = True
        try:
            self._save_btn.configure(state="disabled", text="…")
        except Exception:
            pass

        try:
            if self._template:
                updated = template_service.update(
                    self._template_id,
                    name=name,
                    title=title,
                    category_id=self._category_id,
                    duration_min=duration_min or None,
                    tags=tags,
                    notes=notes,
                    shortcut=shortcut,
                    icon=self._icon,
                    color=self._color,
                )
                try:
                    Toast.show(self,
                                (i18n.t("templateSaved", self._lang)
                                  if i18n.t("templateSaved", self._lang)
                                  != "templateSaved"
                                  else "قالب ذخیره شد"),
                                kind="success", lang=self._lang)
                except Exception:
                    pass
                self._dirty = False
                self.close({"action": "saved", "template": updated})
            else:
                new_t = template_service.add(
                    name=name,
                    title=title,
                    category_id=self._category_id,
                    duration_min=duration_min or None,
                    tags=tags,
                    notes=notes,
                    shortcut=shortcut,
                    icon=self._icon,
                    color=self._color,
                )
                try:
                    Toast.show(self,
                                (i18n.t("templateSaved", self._lang)
                                  if i18n.t("templateSaved", self._lang)
                                  != "templateSaved"
                                  else "قالب ذخیره شد"),
                                kind="success", lang=self._lang)
                except Exception:
                    pass
                self._dirty = False
                self.close({"action": "saved", "template": new_t})
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
    def _on_delete(self) -> None:
        try:
            ConfirmDialog(
                self,
                title=i18n.t("delete", self._lang),
                message=("این قالب حذف شود؟" if self._lang == "fa"
                          else "Delete this template?"),
                danger=True,
                confirm_text=i18n.t("delete", self._lang),
                on_result=self._do_delete,
                lang=self._lang,
            )
        except Exception:
            self._do_delete({"confirmed": True})

    def _do_delete(self, result: Optional[Dict[str, Any]]) -> None:
        if not result or not result.get("confirmed"):
            return
        try:
            template_service.delete(self._template_id)
            try:
                Toast.show(self,
                            (i18n.t("templateDeleted", self._lang)
                              if i18n.t("templateDeleted", self._lang)
                              != "templateDeleted"
                              else "قالب حذف شد"),
                            kind="info", lang=self._lang)
            except Exception:
                pass
            self._dirty = False
            self.close({"action": "deleted",
                         "template_id": self._template_id})
        except Exception as exc:
            self._show_error(str(exc))

    # ------------------------------------------------------------------
    def _on_cancel(self) -> None:
        if self._dirty:
            try:
                ConfirmDialog(
                    self,
                    title=i18n.t("discardActivity", self._lang),
                    message=("تغییرات ذخیره نشده‌اند." if self._lang == "fa"
                              else "Unsaved changes will be lost."),
                    danger=True,
                    confirm_text=i18n.t("discardActivity", self._lang),
                    on_result=lambda r: self.close(
                        {"action": "cancelled"})
                                        if (r and r.get("confirmed")) else None,
                    lang=self._lang,
                )
            except Exception:
                self.close({"action": "cancelled"})
        else:
            self.close({"action": "cancelled"})

    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self._on_cancel(), add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("template_dialog module: 1 class (TemplateDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
