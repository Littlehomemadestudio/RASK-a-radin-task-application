"""
rask.ui.dialogs.category_dialog
===============================

Modal dialog for creating / editing a category.

Layout
------
  * Title row: ``"دسته جدید"`` / ``"ویرایش دسته"``  +  close (×)
  * Persian name (GoldEntry, required)
  * English name (GoldEntry, required)
  * Key (auto-generated from English name, editable, uppercase)
  * Color picker (gold palette + custom)
  * Icon picker grid (ring, book, briefcase, heart, palette, users,
    moon, star, spark, flame, etc.)
  * Save / Cancel / Delete (when editing)

The key field auto-uppercases and slugifies on the fly.  If the user
leaves it empty, it is auto-derived from the English name on save.
"""
from __future__ import annotations

import re
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
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.inputs import GoldEntry
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from .confirm_dialog import ConfirmDialog
from .goal_dialog import _ColorSwatchGrid, GOLD_PALETTE
from .template_dialog import _IconPickerGrid, TEMPLATE_ICONS

__all__ = ["CategoryDialog"]


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _slugify_key(s: str) -> str:
    """Convert a free-form English string into an UPPERCASE_KEY."""
    if not s:
        return ""
    s = s.strip()
    s = _SLUG_RE.sub("_", s)
    s = s.strip("_")
    return s.upper()


# =============================================================================
# === CategoryDialog                                                         ===
# =============================================================================

class CategoryDialog(BaseDialog):
    """Modal create / edit category dialog.

    Parameters
    ----------
    master
        Parent widget.
    category_id
        Optional category id to edit.  ``None`` creates a new category.
    lang
        UI language.
    on_result
        Callback receiving ``{"action": str, "category": dict}``.
    """

    def __init__(
        self,
        master: Any,
        category_id: Optional[int] = None,
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._category_id = category_id
        self._category: Optional[Dict[str, Any]] = None
        if category_id is not None:
            try:
                self._category = db.category_get(int(category_id))
            except Exception:
                self._category = None
        if self._category:
            self._name_fa = self._category.get("name_fa", "")
            self._name_en = self._category.get("name_en", "")
            self._key = self._category.get("key", "")
            self._color = self._category.get("color") or config.GOLD
            self._icon = self._category.get("icon") or "ring"
        else:
            self._name_fa = ""
            self._name_en = ""
            self._key = ""
            self._color = config.GOLD
            self._icon = "ring"
        self._dirty = False
        self._saving = False
        self._auto_key = True  # auto-generate key from English name
        if self._key:
            self._auto_key = False
        kwargs.setdefault("height", 640)
        kwargs.setdefault("width", 480)
        kwargs.setdefault("close_on_overlay", False)
        title = (i18n.t("editCategory", lang) if self._category
                  else i18n.t("newCategory", lang))
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

        # --- Persian name -------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("categoryNameFa", self._lang)
                   if i18n.t("categoryNameFa", self._lang)
                   != "categoryNameFa"
                   else "نام فارسی"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._name_fa_entry = GoldEntry(
            form, lang=self._lang, height=46,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._name_fa_entry.value = self._name_fa
        self._name_fa_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- English name -------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("categoryNameEn", self._lang)
                   if i18n.t("categoryNameEn", self._lang)
                   != "categoryNameEn"
                   else "نام انگلیسی"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._name_en_entry = GoldEntry(
            form, lang="en", height=46,
            on_change=self._on_name_en_change,
        )
        self._name_en_entry.value = self._name_en
        self._name_en_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Key ----------------------------------------------------
        SectionTitle(
            form,
            text=("کلید (لاتین)" if self._lang == "fa" else "Key (latin)"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._key_entry = GoldEntry(
            form, lang="en", height=42,
            on_change=self._on_key_change,
        )
        self._key_entry.value = self._key
        self._key_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
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
        if self._category:
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
    def _on_name_en_change(self, value: str) -> None:
        self._mark_dirty()
        if not self._auto_key:
            return
        # Auto-generate the key from the English name
        new_key = _slugify_key(value)
        if new_key != self._key:
            self._key = new_key
            try:
                self._key_entry.value = new_key
            except Exception:
                pass

    def _on_key_change(self, value: str) -> None:
        self._mark_dirty()
        # Once the user manually edits the key, switch off auto-generation.
        self._auto_key = False
        # Force uppercase on the fly
        upper = value.upper()
        if upper != value:
            try:
                pos = self._key_entry.index("insert")
                self._key_entry.delete(0, "end")
                self._key_entry.insert(0, upper)
                self._key_entry.icursor(pos)
            except Exception:
                pass
        self._key = upper

    def _on_color_change(self, color: str) -> None:
        self._color = color
        self._dirty = True

    def _on_icon_change(self, name: str) -> None:
        self._icon = name
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
        name_fa = self._name_fa_entry.value.strip()
        if not name_fa:
            self._show_error(
                "نام فارسی الزامی است" if self._lang == "fa"
                else "Persian name is required")
            return
        name_en = self._name_en_entry.value.strip()
        if not name_en:
            self._show_error(
                "نام انگلیسی الزامی است" if self._lang == "fa"
                else "English name is required")
            return
        key = self._key_entry.value.strip()
        if not key:
            key = _slugify_key(name_en)
        if not key:
            self._show_error(
                "کلید قابل تولید نیست" if self._lang == "fa"
                else "Cannot generate key")
            return
        # Check for key collision (excluding self when editing)
        try:
            existing = db.category_get_by_key(key)
            if existing and (not self._category_id
                              or int(existing["id"]) != int(self._category_id)):
                self._show_error(
                    "این کلید قبلاً استفاده شده" if self._lang == "fa"
                    else "Key already in use")
                return
        except Exception:
            pass

        self._saving = True
        try:
            self._save_btn.configure(state="disabled", text="…")
        except Exception:
            pass

        try:
            if self._category:
                db.category_update(
                    int(self._category_id),
                    key=key,
                    name_en=name_en,
                    name_fa=name_fa,
                    color=self._color,
                    icon=self._icon,
                )
                updated = db.category_get(int(self._category_id))
                try:
                    Toast.show(self,
                                (i18n.t("categorySaved", self._lang)
                                  if i18n.t("categorySaved", self._lang)
                                  != "categorySaved"
                                  else "دسته ذخیره شد"),
                                kind="success", lang=self._lang)
                except Exception:
                    pass
                self._dirty = False
                self.close({"action": "saved", "category": updated})
            else:
                # Determine order_index (place at the end)
                try:
                    existing_list = db.category_list(include_archived=True)
                    order_index = len(existing_list)
                except Exception:
                    order_index = 0
                new_id = db.category_add(
                    key=key,
                    name_en=name_en,
                    name_fa=name_fa,
                    color=self._color,
                    icon=self._icon,
                    order_index=order_index,
                )
                new_cat = db.category_get(new_id)
                try:
                    Toast.show(self,
                                (i18n.t("categorySaved", self._lang)
                                  if i18n.t("categorySaved", self._lang)
                                  != "categorySaved"
                                  else "دسته ذخیره شد"),
                                kind="success", lang=self._lang)
                except Exception:
                    pass
                self._dirty = False
                self.close({"action": "saved", "category": new_cat})
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
                message=(i18n.t("deleteCategoryConfirm", self._lang)
                          if i18n.t("deleteCategoryConfirm", self._lang)
                          != "deleteCategoryConfirm"
                          else "این دسته و تمام فعالیت‌هایش حذف شوند؟"),
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
            db.category_delete(int(self._category_id))
            try:
                Toast.show(self,
                            (i18n.t("categoryDeleted", self._lang)
                              if i18n.t("categoryDeleted", self._lang)
                              != "categoryDeleted"
                              else "دسته حذف شد"),
                            kind="info", lang=self._lang)
            except Exception:
                pass
            self._dirty = False
            self.close({"action": "deleted",
                         "category_id": self._category_id})
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
    print("category_dialog module: 1 class (CategoryDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
