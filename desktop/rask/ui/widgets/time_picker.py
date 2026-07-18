"""
rask.ui.widgets.time_picker
===========================

Modal time picker with hour/minute steppers and quick presets.

  * ``TimePicker(BottomSheet)``
  * Class method ``TimePicker.ask(parent, initial=None, format_24=True) -> str | None``
    returns ``"HH:MM"``
  * Quick presets: Now, Morning (9 AM), Noon (12 PM), Afternoon (3 PM),
    Evening (6 PM), Night (9 PM)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

import customtkinter as ctk

from ... import config
from ... import i18n
from . import theme as _theme
from .dialogs import BottomSheet
from .inputs import TimeEntry
from .buttons import GoldButton, GhostButton, TextButton
from .dividers import Divider

__all__ = ["TimePicker"]


# =============================================================================
# === TimePicker                                                            ===
# =============================================================================

class TimePicker(BottomSheet):
    """Modal time picker.

    Returns
    -------
    On confirm, ``.result`` is ``"HH:MM"`` (24-hour).  On cancel, None.
    """

    PRESETS: list[tuple[str, int, int]] = [
        ("اکنون" if "fa" else "Now", -1, -1),
        ("صبح" if "fa" else "Morning", 9, 0),
        ("ظهر" if "fa" else "Noon", 12, 0),
        ("بعدازظهر" if "fa" else "Afternoon", 15, 0),
        ("غروب" if "fa" else "Evening", 18, 0),
        ("شب" if "fa" else "Night", 21, 0),
    ]

    def __init__(
        self,
        master: Any = None,
        initial: Optional[str] = None,
        format_24: bool = True,
        on_result: Optional[Callable[[Optional[str]], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._initial = initial or datetime.now().strftime("%H:%M")
        self._format_24 = format_24
        kwargs.setdefault("height", 420)
        super().__init__(master, title="انتخاب زمان" if lang == "fa"
                          else "Pick time", lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        # Large time entry
        self._entry = TimeEntry(
            self._content, lang=self._lang, initial=self._initial,
            format_24=self._format_24, height=60,
        )
        self._entry.pack(fill="x", pady=(0, 12))
        # Quick presets
        ctk.CTkLabel(
            self._content,
            text="پیش‌تنظیم‌ها" if self._lang == "fa" else "Quick presets",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).pack(anchor="e" if rtl else "w", pady=(4, 4))
        preset_grid = ctk.CTkFrame(self._content, fg_color="transparent")
        preset_grid.pack(fill="x", pady=(0, 8))
        cols = 3
        for i in range(cols):
            preset_grid.grid_columnconfigure(i, weight=1)
        for i, (label, h, m) in enumerate(self.PRESETS):
            r, c = divmod(i, cols)
            if rtl:
                c = cols - 1 - c
            btn = TextButton(
                preset_grid, text=label,
                command=lambda hh=h, mm=m: self._set_preset(hh, mm),
                lang=self._lang,
                color=config.TEXT_DIM, hover_color=config.GOLD,
                height=32,
            )
            btn.grid(row=r, column=c, sticky="ew", padx=2, pady=2)
        Divider(self._content).pack(fill="x", pady=8)
        # Action buttons
        btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        cancel = GhostButton(
            btn_row, text="لغو" if self._lang == "fa" else "Cancel",
            command=lambda: self.close(None),
            lang=self._lang, height=42,
        )
        confirm = GoldButton(
            btn_row, text="تأیید" if self._lang == "fa" else "Confirm",
            command=self._confirm,
            lang=self._lang, height=42,
        )
        if rtl:
            confirm.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            confirm.grid(row=0, column=1, sticky="ew", padx=(2, 4))

    # ------------------------------------------------------------------
    def _set_preset(self, hour: int, minute: int) -> None:
        if hour < 0:
            # Now preset
            now = datetime.now()
            hour, minute = now.hour, now.minute
        self._entry.value = f"{hour:02d}:{minute:02d}"

    def _confirm(self) -> None:
        try:
            self._entry.validate()
            self.close(self._entry.value)
        except Exception:
            self.close(None)

    # ------------------------------------------------------------------
    @classmethod
    def ask(
        cls,
        parent: Any,
        initial: Optional[str] = None,
        format_24: bool = True,
        lang: str = "fa",
    ) -> Optional[str]:
        """Open a time picker; returns the picker instance.

        Use ``on_result`` callback to receive the selected time string.
        """
        try:
            return cls(parent, initial=initial, format_24=format_24,
                        lang=lang)
        except Exception:
            return None


def _self_test() -> int:
    classes = [TimePicker]
    print(f"Time picker module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
