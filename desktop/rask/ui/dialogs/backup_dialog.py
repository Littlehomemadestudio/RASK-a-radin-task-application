"""
rask.ui.dialogs.backup_dialog
=============================

Modal dialog for creating an encrypted backup or restoring from one.

Backup mode
-----------
  * Password field (PasswordEntry, required, min 8 chars)
  * Confirm password (PasswordEntry)
  * Strength indicator (weak / medium / strong)
  * "Show password" toggle
  * Hint: "این رمز را در جای امن نگه دار. بدون آن بازگردانی غیرممکن است."
  * "Backup Now" button (gold, full width)
  * Progress indicator during backup
  * Success / failure toast

Restore mode
------------
  * File picker → choose a backup file
  * Password field for the chosen file
  * Restore button → progress → toast

Mirrors ``web/js/app.js :: openBackupDialog`` 1:1.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

try:
    from tkinter import filedialog
    _FD_OK: bool = True
except Exception:  # pragma: no cover
    _FD_OK: False
    filedialog = None  # type: ignore[assignment]

from ... import config
from ... import i18n
from ...core import helpers
from ...services import backup_service, settings_service
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.inputs import PasswordEntry
from ..widgets.toggles import Toggle, CheckBox
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from ..widgets.sliders import ProgressBar
from .confirm_dialog import ConfirmDialog

__all__ = ["BackupDialog"]


# =============================================================================
# === Password strength                                                      ===
# =============================================================================

def _password_strength(pw: str) -> Dict[str, Any]:
    """Estimate password strength on a 0-4 scale.

    Returns ``{"score": int, "label": str, "color": str}``.
    """
    if not pw:
        return {"score": 0, "label": "", "color": config.TEXT_FAINT}
    score = 0
    if len(pw) >= 8:
        score += 1
    if len(pw) >= 12:
        score += 1
    if any(c.isupper() for c in pw) and any(c.islower() for c in pw):
        score += 1
    if any(c.isdigit() for c in pw):
        score += 1
    if any(not c.isalnum() for c in pw):
        score += 1
    score = min(4, score)
    label_map = {
        0: ("خیلی ضعیف" if i18n.get_language() == "fa" else "Very weak"),
        1: ("ضعیف" if i18n.get_language() == "fa" else "Weak"),
        2: ("متوسط" if i18n.get_language() == "fa" else "Medium"),
        3: ("قوی" if i18n.get_language() == "fa" else "Strong"),
        4: ("خیلی قوی" if i18n.get_language() == "fa" else "Very strong"),
    }
    color_map = {
        0: config.DANGER,
        1: config.DANGER,
        2: config.WARNING,
        3: config.SUCCESS,
        4: config.SUCCESS,
    }
    return {
        "score": score,
        "label": label_map[score],
        "color": color_map[score],
    }


# =============================================================================
# === BackupDialog                                                           ===
# =============================================================================

class BackupDialog(BaseDialog):
    """Modal backup / restore dialog.

    Parameters
    ----------
    master
        Parent widget.
    mode
        ``"backup"`` (default) or ``"restore"``.
    lang
        UI language.
    on_result
        Callback receiving ``{"action": str, "success": bool,
        "path": Optional[str], "error": Optional[str]}``.
    """

    def __init__(
        self,
        master: Any,
        mode: str = "backup",
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._mode = mode if mode in ("backup", "restore") else "backup"
        self._selected_path: Optional[str] = None
        self._busy = False
        self._worker_thread: Optional[threading.Thread] = None
        kwargs.setdefault("height", 540)
        kwargs.setdefault("width", 460)
        kwargs.setdefault("close_on_overlay", False)
        title = (i18n.t("backupNow", lang) if mode == "backup"
                  else i18n.t("restoreFromBackup", lang))
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

        # --- File picker (restore mode) ------------------------------
        if self._mode == "restore":
            SectionTitle(
                form,
                text=(i18n.t("backupFile", self._lang)
                       if i18n.t("backupFile", self._lang)
                       != "backupFile"
                       else "فایل پشتیبان"),
                lang=self._lang,
            ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
            row += 1
            file_row = ctk.CTkFrame(form, fg_color="transparent")
            file_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            file_row.grid_columnconfigure(0, weight=1)
            self._file_btn = ctk.CTkButton(
                file_row,
                text=(i18n.t("selectBackup", self._lang)
                       if i18n.t("selectBackup", self._lang)
                       != "selectBackup"
                       else "انتخاب فایل"),
                command=self._pick_file,
                fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
                text_color=config.GOLD,
                border_width=1, border_color=config.SURFACE_HI,
                corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
                anchor="e" if rtl else "w",
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="bold", lang=self._lang),
            )
            self._file_btn.grid(row=0, column=0, sticky="ew")
            row += 1

        # --- Password -----------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("backupPassword", self._lang)
                   if i18n.t("backupPassword", self._lang)
                   != "backupPassword"
                   else "رمز پشتیبان"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._pw_entry = PasswordEntry(
            form, lang=self._lang, height=46,
        )
        self._pw_entry.pack(fill="x", pady=(0, 8))
        try:
            # Hook into the underlying entry's key release
            inner_entry = self._pw_entry._entry  # type: ignore[attr-defined]
            inner_entry.bind("<KeyRelease>", self._on_pw_change, add="+")
        except Exception:
            pass

        # --- Confirm password (backup mode only) --------------------
        if self._mode == "backup":
            SectionTitle(
                form,
                text=(i18n.t("confirmPin", self._lang)
                       if i18n.t("confirmPin", self._lang) != "confirmPin"
                       else "تکر رمز"),
                lang=self._lang,
            ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
            row += 1
            self._pw_confirm = PasswordEntry(
                form, lang=self._lang, height=46,
            )
            self._pw_confirm.pack(fill="x", pady=(0, 8))
            try:
                inner = self._pw_confirm._entry  # type: ignore[attr-defined]
                inner.bind("<KeyRelease>", self._on_pw_change, add="+")
            except Exception:
                pass

        # --- Strength indicator (backup mode only) ------------------
        if self._mode == "backup":
            strength_row = ctk.CTkFrame(form, fg_color="transparent")
            strength_row.pack(fill="x", pady=(0, 8))
            strength_row.grid_columnconfigure(0, weight=1)
            strength_row.grid_columnconfigure(1, weight=0)
            self._strength_bar = ProgressBar(
                strength_row, value=0, height=6,
            )
            self._strength_bar.grid(row=0, column=0, sticky="ew", padx=4)
            self._strength_label = ctk.CTkLabel(
                strength_row, text="",
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.TEXT_DIM,
            )
            self._strength_label.grid(row=0, column=1, padx=4)

        # --- Show password toggle (common) --------------------------
        show_row = ctk.CTkFrame(form, fg_color="transparent")
        show_row.pack(fill="x", pady=(0, 8))
        show_row.grid_columnconfigure(0, weight=1)
        show_row.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(
            show_row,
            text=("نمایش رمز" if self._lang == "fa" else "Show password"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        self._show_toggle = Toggle(
            show_row, text="", on_change=self._on_show_toggle,
            lang=self._lang,
        )
        self._show_toggle.grid(row=0, column=1, padx=4)

        # --- Hint ---------------------------------------------------
        if self._mode == "backup":
            hint_text = ("این رمز را در جای امن نگه دار. بدون آن "
                          "بازگردانی غیرممکن است." if self._lang == "fa"
                          else "Keep this password safe. Restoration is "
                               "impossible without it.")
            ctk.CTkLabel(
                form, text=hint_text,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.WARNING,
                anchor="e" if rtl else "w",
                justify="right" if rtl else "left",
                wraplength=380,
            ).pack(fill="x", pady=(0, 8))

        # --- Error caption ------------------------------------------
        self._error_label = ctk.CTkLabel(
            form, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.DANGER,
            anchor="e" if rtl else "w",
            wraplength=380, justify="right" if rtl else "left",
        )
        self._error_label.pack(fill="x", pady=(0, 4))

        # --- Progress bar (hidden until busy) -----------------------
        self._progress = ProgressBar(form, value=0.0, height=6)
        self._progress.pack(fill="x", pady=(0, 4))
        try:
            self._progress.set(0.0)
        except Exception:
            pass

        Divider(form).pack(fill="x", pady=(4, 8))

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
        action_text = (i18n.t("backupNow", self._lang)
                        if self._mode == "backup"
                        else i18n.t("restore", self._lang))
        self._action_btn = GoldButton(
            btn_row, text=action_text,
            command=self._on_action,
            lang=self._lang, height=46,
            icon_name=("backup" if self._mode == "backup" else "restore"),
            icon_size=16,
        )
        if rtl:
            self._action_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._action_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))

    # ------------------------------------------------------------------
    def _pick_file(self) -> None:
        if not _FD_OK:
            return
        try:
            initial_dir = str(config.BACKUP_DIR)
            path = filedialog.askopenfilename(
                title=(i18n.t("selectBackup", self._lang)
                        if i18n.t("selectBackup", self._lang)
                        != "selectBackup"
                        else "Select backup file"),
                initialdir=initial_dir,
                filetypes=[("Rask Backup", "*.raskbk"),
                            ("All files", "*.*")],
            )
            if path:
                self._selected_path = path
                try:
                    name = os.path.basename(path)
                    self._file_btn.configure(text=name)
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_pw_change(self, _evt: Any = None) -> None:
        if self._mode != "backup":
            return
        try:
            pw = self._pw_entry.value
            strength = _password_strength(pw)
            # Update bar
            try:
                self._strength_bar.set_value(strength["score"] / 4.0)
            except Exception:
                pass
            try:
                self._strength_bar.configure(
                    progress_color=strength["color"])
            except Exception:
                pass
            self._strength_label.configure(
                text=strength["label"], text_color=strength["color"])
        except Exception:
            pass

    def _on_show_toggle(self, value: bool) -> None:
        try:
            # Toggle the PasswordEntry's underlying entry show attribute
            inner = self._pw_entry._entry  # type: ignore[attr-defined]
            show_char = "" if value else "•"
            try:
                inner._entry.configure(show=show_char)  # type: ignore[attr-defined]
            except Exception:
                inner.configure(show=show_char)
        except Exception:
            pass
        if self._mode == "backup":
            try:
                inner2 = self._pw_confirm._entry  # type: ignore[attr-defined]
                show_char = "" if value else "•"
                try:
                    inner2._entry.configure(show=show_char)  # type: ignore[attr-defined]
                except Exception:
                    inner2.configure(show=show_char)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _show_error(self, msg: str) -> None:
        try:
            self._error_label.configure(text=msg)
        except Exception:
            pass

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        try:
            self._action_btn.configure(
                state="disabled" if busy else "normal",
                text="…" if busy else (
                    i18n.t("backupNow", self._lang)
                    if self._mode == "backup"
                    else i18n.t("restore", self._lang)),
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_action(self) -> None:
        if self._busy:
            return
        if not backup_service.is_available():
            self._show_error(
                "بسته رمزنگاری در دسترس نیست" if self._lang == "fa"
                else "Cryptography package unavailable")
            return
        pw = self._pw_entry.value
        if len(pw) < 8:
            self._show_error(
                "رمز باید حداقل ۸ نویسه باشد" if self._lang == "fa"
                else "Password must be at least 8 characters")
            return
        if self._mode == "backup":
            confirm_pw = self._pw_confirm.value
            if pw != confirm_pw:
                self._show_error(
                    "رمزها مطابقت ندارند" if self._lang == "fa"
                    else "Passwords do not match")
                return
            self._start_backup(pw)
        else:
            if not self._selected_path:
                self._show_error(
                    "یک فایل پشتیبان انتخاب کن" if self._lang == "fa"
                    else "Please select a backup file")
                return
            self._start_restore(self._selected_path, pw)

    # ------------------------------------------------------------------
    def _start_backup(self, password: str) -> None:
        self._set_busy(True)
        try:
            self._progress.set(0.2)
        except Exception:
            pass

        def worker() -> None:
            try:
                result = backup_service.create(password)
            except Exception as exc:  # noqa: BLE001
                result = {"success": False, "error": str(exc),
                            "path": None, "size": 0}
            try:
                self.after(0, lambda: self._on_backup_done(result))
            except Exception:
                pass

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()
        self._animate_progress(0.2, 0.8, step=0.05)

    def _on_backup_done(self, result: Dict[str, Any]) -> None:
        self._set_busy(False)
        try:
            self._progress.set(1.0 if result.get("success") else 0.0)
        except Exception:
            pass
        if result.get("success"):
            try:
                Toast.show(
                    self,
                    (i18n.t("backupCreated", self._lang)
                      if i18n.t("backupCreated", self._lang)
                      != "backupCreated"
                      else "پشتیبان ساخته شد"),
                    kind="success", lang=self._lang,
                )
            except Exception:
                pass
            try:
                settings_service.set_last_backup_iso(
                    result.get("timestamp", ""))
            except Exception:
                pass
            self.close({
                "action": "backup", "success": True,
                "path": result.get("path"),
                "error": None,
            })
        else:
            self._show_error(
                result.get("error") or
                ("پشتیبان‌گیری ناموفق" if self._lang == "fa"
                  else "Backup failed"))
            try:
                self.after(1500, lambda: self._progress.set(0.0))
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _start_restore(self, path: str, password: str) -> None:
        # Confirm destructive restore
        try:
            ConfirmDialog(
                self,
                title=i18n.t("restoreFromBackup", self._lang),
                message=("بازگردانی داده‌های فعلی را جایگزین می‌کند. "
                          "آیا مطمئنی؟" if self._lang == "fa"
                          else "Restore replaces current data. Continue?"),
                danger=True,
                confirm_text=i18n.t("restore", self._lang),
                on_result=lambda r: self._do_restore(r, path, password),
                lang=self._lang,
            )
        except Exception:
            self._do_restore({"confirmed": True}, path, password)

    def _do_restore(self, result: Optional[Dict[str, Any]],
                     path: str, password: str) -> None:
        if not result or not result.get("confirmed"):
            return
        self._set_busy(True)
        try:
            self._progress.set(0.2)
        except Exception:
            pass

        def worker() -> None:
            try:
                result = backup_service.restore(path, password)
            except Exception as exc:  # noqa: BLE001
                result = {"success": False, "error": str(exc),
                            "path": path, "record_count": 0}
            try:
                self.after(0, lambda: self._on_restore_done(result))
            except Exception:
                pass

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()
        self._animate_progress(0.2, 0.8, step=0.05)

    def _on_restore_done(self, result: Dict[str, Any]) -> None:
        self._set_busy(False)
        try:
            self._progress.set(1.0 if result.get("success") else 0.0)
        except Exception:
            pass
        if result.get("success"):
            try:
                Toast.show(
                    self,
                    (i18n.t("restoreSuccess", self._lang)
                      if i18n.t("restoreSuccess", self._lang)
                      != "restoreSuccess"
                      else "بازگردانی موفق"),
                    kind="success", lang=self._lang,
                )
            except Exception:
                pass
            self.close({
                "action": "restore", "success": True,
                "path": result.get("path"),
                "error": None,
                "record_count": result.get("record_count", 0),
            })
        else:
            err = result.get("error", "")
            label = err
            if err == "wrong password":
                label = (i18n.t("wrongPassword", self._lang)
                          if i18n.t("wrongPassword", self._lang)
                          != "wrongPassword"
                          else "رمز اشتباه")
            elif err:
                label = err
            self._show_error(label or
                              (i18n.t("restoreFailed", self._lang)
                                if i18n.t("restoreFailed", self._lang)
                                != "restoreFailed"
                                else "بازگردانی ناموفق"))
            try:
                self.after(1500, lambda: self._progress.set(0.0))
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _animate_progress(self, start: float, end: float,
                            step: float = 0.05) -> None:
        """Cycle the progress bar between start and end while busy."""
        if not self._busy:
            return
        try:
            cur = start + step
            if cur >= end:
                cur = start + step  # loop back
            self._progress.set(cur)
        except Exception:
            pass
        try:
            self.after(220, lambda: self._animate_progress(start, end, step))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_cancel(self) -> None:
        if self._busy:
            # Don't allow cancelling mid-operation
            return
        self.close({"action": "cancelled", "success": False,
                     "path": None, "error": None})

    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self._on_cancel(), add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("backup_dialog module: 1 class (BackupDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
