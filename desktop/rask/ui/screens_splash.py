"""screens_splash.py — Splash, Onboarding, and Lock screens.

Mirror of:
  - web/index.html #splash  (animated R logo + appName + tagline)
  - web/index.html #onboarding (3-slide intro with dots + Skip/Next)
  - web/index.html #lock (R logo + appName + PIN entry + Unlock button)
"""
from __future__ import annotations
import tkinter as tk
from typing import Callable, Optional

from .. import config
from .. import database
from .. import crypto
from ..i18n import t, to_fa_digits
from .. import widgets
from ..widgets import (
    GoldButton, IconButton, Field, Avatar, get_font,
    section_header, greeting_label, date_label,
)


# =====================================================================
# === SPLASH SCREEN ===
# =====================================================================
class SplashView(tk.Frame):
    """The splash screen. Shows R logo + appName + tagline, then calls on_done."""
    def __init__(self, parent, on_done: Callable[[], None],
                 lang: str = "fa", duration_ms: int = 2200, **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK, **kwargs)
        self._on_done = on_done
        self._lang = lang
        self._duration_ms = duration_ms
        # Center everything
        container = tk.Frame(self, bg=config.MATTE_BLACK)
        container.place(relx=0.5, rely=0.5, anchor="center")
        # Animated avatar (R letter with pulsing gold ring)
        self._avatar = Avatar(container, letter="R", size=180,
                               color=config.GOLD, animated=True, bg=config.MATTE_BLACK)
        self._avatar.pack(pady=(0, 24))
        # App name
        tk.Label(container, text=t("appName", lang), bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=get_font(42, "bold")).pack(pady=(0, 8))
        # Tagline
        tk.Label(container, text=t("tagline", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(13)).pack()
        # Schedule dismissal
        self.after(duration_ms, self._finish)

    def _finish(self):
        self._avatar.stop_animation()
        try:
            self._on_done()
        except Exception:
            pass


# =====================================================================
# === ONBOARDING SCREEN ===
# =====================================================================
class OnboardingView(tk.Frame):
    """The 3-slide onboarding flow."""
    SLIDES = [
        ("slide1Title", "slide1Body"),
        ("slide2Title", "slide2Body"),
        ("slide3Title", "slide3Body"),
    ]

    def __init__(self, parent, lang: str = "fa",
                 on_done: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK, **kwargs)
        self._lang = lang
        self._on_done = on_done
        self._index = 0
        self._build()
        self._render()

    def _build(self):
        # Top illustration (circle)
        top = tk.Frame(self, bg=config.MATTE_BLACK)
        top.pack(fill="x", pady=(48, 24))
        self._illustration = tk.Canvas(top, width=200, height=200,
                                        bg=config.MATTE_BLACK,
                                        highlightthickness=0, bd=0)
        self._illustration.pack()
        # Title
        self._title_var = tk.StringVar()
        tk.Label(self, textvariable=self._title_var, bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=get_font(28, "bold"),
                 wraplength=440).pack(pady=(24, 12))
        # Body
        self._body_var = tk.StringVar()
        tk.Label(self, textvariable=self._body_var, bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(15),
                 wraplength=440, justify="center").pack(pady=(0, 24))
        # Dots
        self._dots_frame = tk.Frame(self, bg=config.MATTE_BLACK)
        self._dots_frame.pack(pady=(16, 32))
        # Buttons
        btn_frame = tk.Frame(self, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", padx=24, pady=(0, 32), side="bottom")
        self._skip_btn = GoldButton(btn_frame, text=t("skip", self._lang),
                                      command=self._on_skip, kind="outline",
                                      full_width=True)
        self._skip_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._next_btn = GoldButton(btn_frame, text=t("next", self._lang),
                                      command=self._on_next, kind="gold",
                                      full_width=True)
        self._next_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))

    def _render(self):
        # Update illustration
        self._illustration.delete("all")
        # Pulsing gold ring with spinning inner ring (mirror CSS animation)
        cx, cy = 100, 100
        # Outer ring
        self._illustration.create_oval(cx - 80, cy - 80, cx + 80, cy + 80,
                                        outline=config.GOLD, width=4)
        # Inner spinning ring (just draw a circle; can't actually animate easily)
        self._illustration.create_oval(cx - 60, cy - 60, cx + 60, cy + 60,
                                        outline=config.GOLD_SOFT, width=8)
        # Slide number in center
        self._illustration.create_text(cx, cy, text=str(self._index + 1),
                                        fill=config.GOLD, font=get_font(48, "bold"))
        # Update title/body
        title_key, body_key = self.SLIDES[self._index]
        self._title_var.set(t(title_key, self._lang))
        self._body_var.set(t(body_key, self._lang))
        # Update dots
        for child in self._dots_frame.winfo_children():
            child.destroy()
        for i in range(len(self.SLIDES)):
            color = config.GOLD if i == self._index else config.TEXT_FAINT
            width = 24 if i == self._index else 8
            dot = tk.Frame(self._dots_frame, bg=color, width=width, height=8)
            dot.pack(side="left", padx=4)
        # Update button labels
        if self._index == len(self.SLIDES) - 1:
            self._next_btn.set_text(t("start", self._lang))
        else:
            self._next_btn.set_text(t("next", self._lang))

    def _on_next(self):
        self._index += 1
        if self._index >= len(self.SLIDES):
            self._finish()
        else:
            self._render()

    def _on_skip(self):
        self._finish()

    def _finish(self):
        database.kv_set("first_run", "0")
        database.kv_set("onboarded", "1")
        if self._on_done:
            try:
                self._on_done()
            except Exception:
                pass


# =====================================================================
# === LOCK SCREEN ===
# =====================================================================
class LockView(tk.Frame):
    """The PIN lock screen."""
    def __init__(self, parent, lang: str = "fa",
                 on_unlock: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK, **kwargs)
        self._lang = lang
        self._on_unlock = on_unlock
        self._build()

    def _build(self):
        # Center
        container = tk.Frame(self, bg=config.MATTE_BLACK)
        container.place(relx=0.5, rely=0.5, anchor="center")
        # R logo (non-animated)
        avatar = Avatar(container, letter="R", size=120,
                         color=config.GOLD, bg=config.MATTE_BLACK)
        avatar.pack(pady=(0, 24))
        # App name
        tk.Label(container, text=t("appName", self._lang),
                 bg=config.MATTE_BLACK, fg=config.GOLD,
                 font=get_font(24, "bold")).pack(pady=(0, 8))
        # Subtitle
        tk.Label(container, text=t("unlockRask", self._lang),
                 bg=config.MATTE_BLACK, fg=config.TEXT_DIM,
                 font=get_font(12)).pack(pady=(0, 32))
        # PIN entry
        self._pin_var = tk.StringVar()
        self._pin_entry = tk.Entry(container, textvariable=self._pin_var,
                                    show="*", bg=config.MATTE_BLACK,
                                    fg=config.TEXT, insertbackground=config.GOLD,
                                    font=get_font(20, "bold"), relief="flat",
                                    bd=0, justify="center", width=10,
                                    highlightbackground=config.GOLD,
                                    highlightthickness=2)
        self._pin_entry.pack(pady=(0, 16), ipady=8, ipadx=16)
        self._pin_entry.focus_set()
        self._pin_entry.bind("<Return>", lambda e: self._try_unlock())
        # Unlock button
        self._unlock_btn = GoldButton(container, text=t("unlock", self._lang),
                                        command=self._try_unlock, kind="gold",
                                        full_width=True)
        self._unlock_btn.configure(width=200)
        self._unlock_btn.pack(pady=(0, 8))
        # Error label
        self._error_var = tk.StringVar()
        self._error_label = tk.Label(container, textvariable=self._error_var,
                                      bg=config.MATTE_BLACK, fg=config.DANGER,
                                      font=get_font(11))
        self._error_label.pack()

    def _try_unlock(self):
        pin = self._pin_var.get()
        if not pin:
            return
        stored = database.kv_get("pin_hash")
        if stored and crypto.check_pin(pin, stored):
            self._error_var.set("")
            if self._on_unlock:
                try:
                    self._on_unlock()
                except Exception:
                    pass
        else:
            self._error_var.set(t("wrongPin", self._lang))
            self._pin_var.set("")
            # Shake animation would go here

    def set_lang(self, lang: str):
        self._lang = lang
        # Re-render would be complex — caller should recreate the view
