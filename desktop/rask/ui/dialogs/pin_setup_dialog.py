"""
rask.ui.dialogs.pin_setup_dialog
================================

Modal two-step PIN setup dialog.

Flow
----
  * **Step 1** — Enter a 4-digit PIN (``PinEntry``)
  * **Step 2** — Confirm the PIN by re-entering it

Behaviour
---------
  * On mismatch: shake animation + restart from step 1 with an error
    message "پین‌ها مطابقت ندارند".
  * On success: hash via :func:`rask.core.pin.hash_pin`, store via
    ``settings_service.set_pin_hash()``, show a success toast
    "پین تنظیم شد".
  * Security note displayed at the bottom: "این پین برای باز کردن قفل
    برنامه استفاده می‌شود".
  * If editing an existing PIN (``mode="change"``), a "حذف پین" button is
    shown — confirms then clears the stored hash via
    ``settings_service.clear_pin_hash()``.

Modes
-----
``mode="setup"``  — initial PIN setup (default)
``mode="change"`` — change existing PIN (shows "حذف پین" button)
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import pin as pin_core
from ...services import settings_service
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.inputs import PinEntry
from ..widgets.dividers import Divider
from ..widgets.toasts import Toast
from .confirm_dialog import ConfirmDialog

__all__ = ["PinSetupDialog"]


# =============================================================================
# === Shake animation helper                                                 ===
# =============================================================================

def _shake_widget(widget: Any, amplitude: int = 8,
                   duration_ms: int = 400) -> None:
    """Apply a brief horizontal shake animation to `widget`.

    Used to signal PIN mismatch.
    """
    try:
        steps = max(6, duration_ms // 32)
        orig_x = widget.winfo_x()

        def tick(step: int) -> None:
            if step >= steps:
                try:
                    widget.place_configure(x=orig_x)
                except Exception:
                    pass
                return
            # Decaying sine wave
            t = step / steps
            decay = 1.0 - t
            offset = int(amplitude * decay *
                          math.sin(step * 1.4))
            try:
                widget.place_configure(x=orig_x + offset)
            except Exception:
                pass
            widget.after(32, lambda: tick(step + 1))

        tick(0)
    except Exception:
        pass


# =============================================================================
# === PinSetupDialog                                                         ===
# =============================================================================

class PinSetupDialog(BaseDialog):
    """Two-step PIN setup / change dialog.

    Parameters
    ----------
    master
        Parent widget.
    mode
        ``"setup"`` for first-time setup, ``"change"`` for changing an
        existing PIN (adds a "Remove PIN" button).
    lang
        UI language.
    on_result
        Callback receiving ``{"action": str}`` where ``action`` is one
        of ``"set"`` / ``"removed"`` / ``"cancelled"``.
    """

    STEP_ENTER = "enter"
    STEP_CONFIRM = "confirm"

    def __init__(
        self,
        master: Any,
        mode: str = "setup",
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._mode = mode if mode in ("setup", "change") else "setup"
        self._step = self.STEP_ENTER
        self._first_pin: str = ""
        self._shake_job = None
        kwargs.setdefault("height", 420)
        kwargs.setdefault("width", 420)
        kwargs.setdefault("close_on_overlay", False)
        title = (i18n.t("changePin", lang) if mode == "change"
                  else i18n.t("setPin", lang))
        super().__init__(master, title=title, lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    # ------------------------------------------------------------------
    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        # Step indicator (1/2)
        self._step_label = ctk.CTkLabel(
            self._content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="center",
        )
        self._step_label.pack(anchor="center", pady=(0, 4))

        # Hint label (e.g. "Enter a 4-digit PIN")
        self._hint_label = ctk.CTkLabel(
            self._content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            anchor="center", justify="center",
            wraplength=360,
        )
        self._hint_label.pack(fill="x", pady=(0, 16))

        # PIN entry
        pin_frame = ctk.CTkFrame(self._content, fg_color="transparent")
        pin_frame.pack(anchor="center", pady=(0, 12))
        self._pin_entry = PinEntry(
            pin_frame, length=4, lang=self._lang, box_size=56, gap=14,
            on_complete=self._on_pin_complete,
        )
        self._pin_entry.pack(anchor="center")

        # Error label
        self._error_label = ctk.CTkLabel(
            self._content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.DANGER,
            anchor="center", justify="center", wraplength=360,
        )
        self._error_label.pack(fill="x", pady=(0, 12))

        # Security note
        self._note_label = ctk.CTkLabel(
            self._content,
            text=("این پین برای باز کردن قفل برنامه استفاده می‌شود"
                    if self._lang == "fa"
                    else "This PIN is used to unlock the app."),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="center", justify="center", wraplength=360,
        )
        self._note_label.pack(fill="x", pady=(0, 12))

        Divider(self._content).pack(fill="x", pady=(4, 8))

        # Buttons
        btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        if self._mode == "change":
            # Add a "remove PIN" button on the side
            remove_btn = TextButton(
                btn_row,
                text=(i18n.t("removePin", self._lang)
                       if i18n.t("removePin", self._lang) != "removePin"
                       else "حذف پین"),
                command=self._on_remove_pin,
                lang=self._lang, height=42,
                color=config.DANGER, hover_color=config.DANGER_DIM,
            )
            remove_btn.grid(row=0, column=0, sticky="ew", padx=2)
            cancel_btn = GhostButton(
                btn_row,
                text=(i18n.t("cancel", self._lang)
                       if i18n.t("cancel", self._lang) != "cancel"
                       else "انصراف"),
                command=lambda: self.close({"action": "cancelled"}),
                lang=self._lang, height=42,
            )
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=2)
        else:
            cancel_btn = GhostButton(
                btn_row,
                text=(i18n.t("cancel", self._lang)
                       if i18n.t("cancel", self._lang) != "cancel"
                       else "انصراف"),
                command=lambda: self.close({"action": "cancelled"}),
                lang=self._lang, height=42,
            )
            cancel_btn.grid(row=0, column=0, sticky="ew", padx=2,
                             columnspan=2)

        # Set up initial step UI
        self._update_step_ui()
        # Auto-focus the PIN entry after a short delay
        try:
            self.after(220, lambda: self._pin_entry.focus_set())
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _update_step_ui(self) -> None:
        if self._step == self.STEP_ENTER:
            self._step_label.configure(
                text=(f"۱/۲  •  {i18n.t('enterPin', self._lang)}"
                       if self._lang == "fa"
                       else f"1/2  •  {i18n.t('enterPin', self._lang)}"))
            self._hint_label.configure(
                text=("یک پین ۴ رقمی انتخاب کن" if self._lang == "fa"
                       else "Choose a 4-digit PIN"))
        else:
            self._step_label.configure(
                text=(f"۲/۲  •  {i18n.t('confirmPin', self._lang)}"
                       if self._lang == "fa"
                       else f"2/2  •  {i18n.t('confirmPin', self._lang)}"))
            self._hint_label.configure(
                text=("پین را دوباره وارد کن" if self._lang == "fa"
                       else "Re-enter the PIN"))

    # ------------------------------------------------------------------
    def _on_pin_complete(self, value: str) -> None:
        if self._step == self.STEP_ENTER:
            self._first_pin = value
            self._step = self.STEP_CONFIRM
            self._pin_entry.clear()
            self._update_step_ui()
            try:
                self._error_label.configure(text="")
            except Exception:
                pass
        else:
            # Confirm step
            if value == self._first_pin:
                self._save_pin(value)
            else:
                # Mismatch — shake + restart
                self._handle_mismatch()

    # ------------------------------------------------------------------
    def _handle_mismatch(self) -> None:
        # Show error
        try:
            self._error_label.configure(
                text=(i18n.t("pinMismatch", self._lang)
                       if i18n.t("pinMismatch", self._lang)
                       != "pinMismatch"
                       else "پین‌ها مطابقت ندارند"))
        except Exception:
            pass
        # Shake the PIN entry
        _shake_widget(self._pin_entry, amplitude=10, duration_ms=420)
        # Restart from step 1
        try:
            self.after(450, self._reset_to_step_1)
        except Exception:
            self._reset_to_step_1()

    def _reset_to_step_1(self) -> None:
        self._step = self.STEP_ENTER
        self._first_pin = ""
        self._pin_entry.clear()
        self._update_step_ui()

    # ------------------------------------------------------------------
    def _save_pin(self, pin_value: str) -> None:
        try:
            # Validate format
            if not pin_core.is_pin_format(pin_value):
                raise ValueError("Invalid PIN format")
            # Hash and store
            pin_hash = pin_core.hash_pin(pin_value)
            settings_service.set_pin_hash(pin_hash)
            try:
                Toast.show(
                    self,
                    (i18n.t("pinSet", self._lang)
                      if i18n.t("pinSet", self._lang) != "pinSet"
                      else "پین تنظیم شد"),
                    kind="success", lang=self._lang,
                )
            except Exception:
                pass
            self.close({"action": "set"})
        except Exception as exc:
            try:
                self._error_label.configure(text=str(exc))
            except Exception:
                pass
            self._reset_to_step_1()

    # ------------------------------------------------------------------
    def _on_remove_pin(self) -> None:
        try:
            ConfirmDialog(
                self,
                title=i18n.t("removePin", self._lang),
                message=("حذف پین باعث می‌شود برنامه بدون قفل باز شود."
                          if self._lang == "fa"
                          else "Removing the PIN disables app lock."),
                danger=True,
                confirm_text=i18n.t("removePin", self._lang),
                on_result=self._do_remove_pin,
                lang=self._lang,
            )
        except Exception:
            self._do_remove_pin({"confirmed": True})

    def _do_remove_pin(self, result: Optional[Dict[str, Any]]) -> None:
        if not result or not result.get("confirmed"):
            return
        try:
            settings_service.clear_pin_hash()
            try:
                Toast.show(self,
                            (i18n.t("pinRemoved", self._lang)
                              if i18n.t("pinRemoved", self._lang)
                              != "pinRemoved"
                              else "پین حذف شد"),
                            kind="info", lang=self._lang)
            except Exception:
                pass
            self.close({"action": "removed"})
        except Exception as exc:
            try:
                self._error_label.configure(text=str(exc))
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>",
                       lambda _e: self.close({"action": "cancelled"}),
                       add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("pin_setup_dialog module: 1 class (PinSetupDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
