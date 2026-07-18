"""screens_splash.py — Splash + Onboarding + Lock screens.

Mirror of:
  - web/index.html #splash (gold ring + R + title + tagline, 2.2s)
  - web/index.html #onboarding (3 slides: title, body, dots, Skip/Next)
  - web/index.html #lock (R logo + appName + unlockRask + PIN entry + Unlock button)
"""
from __future__ import annotations
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional
from .. import config
from ..i18n import t
from .theme import font, family


class SplashView(tk.Frame):
    """Auto-advances after 2.2s — mirror of #splash with fadeOut animation 0.4s 2s."""

    def __init__(self, parent: tk.Widget, on_done: Callable[[], None]):
        super().__init__(parent, bg=config.MATTE_BLACK)
        self.on_done = on_done
        self._build()
        self.after(2200, self._advance)

    def _build(self):
        # Centered: logo (gold ring + R), title, tagline
        container = tk.Frame(self, bg=config.MATTE_BLACK)
        container.place(relx=0.5, rely=0.5, anchor="center")
        # The "R" inside a gold ring — drawn on a Canvas
        cv = tk.Canvas(container, width=180, height=180,
                       bg=config.MATTE_BLACK, highlightthickness=0)
        cv.create_oval(8, 8, 172, 172, outline=config.GOLD, width=4)
        cv.create_text(90, 90, text="R", fill=config.GOLD,
                       font=font(96, "bold"))
        cv.pack(pady=(0, 24))
        title = tk.Label(container, text=t("appName", "fa"), bg=config.MATTE_BLACK,
                         fg=config.GOLD, font=font(42, "bold"))
        title.pack()
        tag = tk.Label(container, text=t("tagline", "fa"), bg=config.MATTE_BLACK,
                       fg=config.TEXT_DIM, font=font(13, "normal"))
        tag.pack(pady=(8, 0))

    def _advance(self):
        try:
            self.on_done()
        finally:
            self.destroy()


class OnboardingView(tk.Frame):
    """3-slide onboarding — mirror of #onboarding with dots + Skip/Next."""

    SLIDES = [
        ("slide1Title", "slide1Body"),
        ("slide2Title", "slide2Body"),
        ("slide3Title", "slide3Body"),
    ]

    def __init__(self, parent: tk.Widget, lang: str, on_done: Callable[[], None]):
        super().__init__(parent, bg=config.MATTE_BLACK)
        self.lang = lang
        self.on_done = on_done
        self.idx = 0
        self._build()
        self._render()

    def _build(self):
        # Top illustration: gold circle + spinning inner ring
        top = tk.Frame(self, bg=config.MATTE_BLACK)
        top.pack(fill="x", pady=(48, 24))
        self.cv = tk.Canvas(top, width=180, height=180,
                            bg=config.MATTE_BLACK, highlightthickness=0)
        self.cv.pack()
        self._draw_illustration()

        # Title + body
        self.title_lbl = tk.Label(self, bg=config.MATTE_BLACK, fg=config.GOLD,
                                   font=font(32, "bold"))
        self.title_lbl.pack(pady=(8, 12))
        self.body_lbl = tk.Label(self, bg=config.MATTE_BLACK, fg=config.TEXT_DIM,
                                  font=font(15), wraplength=440, justify="center")
        self.body_lbl.pack(pady=(0, 24), padx=24, fill="x")

        # Dots
        self.dots = tk.Frame(self, bg=config.MATTE_BLACK)
        self.dots.pack(pady=(16, 24))
        self.dot_widgets = []
        for i in range(3):
            d = tk.Frame(self.dots, bg=config.TEXT_FAINT, width=8, height=8)
            d.pack(side="left", padx=4)
            self.dot_widgets.append(d)

        # Buttons: Skip | Next
        btns = tk.Frame(self, bg=config.MATTE_BLACK)
        btns.pack(fill="x", padx=24, pady=(0, 48))
        from .theme import styled_button
        self.skip_btn = styled_button(btns, "outline", t("skip", self.lang),
                                       command=self._skip, small=False)
        self.skip_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.next_btn = styled_button(btns, "gold", t("next", self.lang),
                                       command=self._next, small=False)
        self.next_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _draw_illustration(self):
        # Outer ring
        self.cv.create_oval(8, 8, 172, 172, outline=config.GOLD, width=4)
        # Inner spinning ring (static here — no animation; CSS animation not replicated)
        self.cv.create_oval(28, 28, 152, 152, outline=config.GOLD_SOFT, width=8)

    def _render(self):
        tk_btn, tk_body = self.SLIDES[self.idx]
        self.title_lbl.config(text=t(tk_btn, self.lang))
        self.body_lbl.config(text=t(tk_body, self.lang))
        for i, d in enumerate(self.dot_widgets):
            if i == self.idx:
                d.config(bg=config.GOLD, width=24, height=8)
            else:
                d.config(bg=config.TEXT_FAINT, width=8, height=8)
        # Last slide: button says "Get started"
        if self.idx == len(self.SLIDES) - 1:
            self.next_btn.config(text=t("start", self.lang))
        else:
            self.next_btn.config(text=t("next", self.lang))

    def _next(self):
        if self.idx < len(self.SLIDES) - 1:
            self.idx += 1
            self._render()
        else:
            self.on_done()
            self.destroy()

    def _skip(self):
        self.on_done()
        self.destroy()


class LockView(tk.Frame):
    """PIN entry — mirror of #lock-screen."""

    def __init__(self, parent: tk.Widget, lang: str, on_unlock: Callable[[], None]):
        super().__init__(parent, bg=config.MATTE_BLACK)
        self.lang = lang
        self.on_unlock = on_unlock
        self._build()

    def _build(self):
        from .theme import styled_button, field
        container = tk.Frame(self, bg=config.MATTE_BLACK)
        container.place(relx=0.5, rely=0.5, anchor="center")

        cv = tk.Canvas(container, width=120, height=120,
                       bg=config.MATTE_BLACK, highlightthickness=0)
        cv.create_oval(6, 6, 114, 114, outline=config.GOLD, width=4)
        cv.create_text(60, 60, text="R", fill=config.GOLD, font=font(56, "bold"))
        cv.pack(pady=(0, 24))

        tk.Label(container, text=t("appName", self.lang), bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=font(24, "bold")).pack(pady=(0, 8))
        tk.Label(container, text=t("unlockRask", self.lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=font(12)).pack(pady=(0, 24))

        self.pin_entry = tk.Entry(container, show="•", justify="center",
                                   bg=config.MATTE_BLACK, fg=config.TEXT,
                                   insertbackground=config.GOLD,
                                   font=font(18), width=12, relief="flat",
                                   highlightbackground=config.GOLD,
                                   highlightthickness=2)
        self.pin_entry.pack(pady=(0, 16), ipady=8)
        self.pin_entry.focus_set()
        self.pin_entry.bind("<Return>", lambda _e: self._try_unlock())

        self.error_lbl = tk.Label(container, text="", bg=config.MATTE_BLACK,
                                   fg=config.DANGER, font=font(11))
        self.error_lbl.pack(pady=(0, 8))

        self.unlock_btn = styled_button(container, "gold", t("unlock", self.lang),
                                         command=self._try_unlock)
        self.unlock_btn.pack(fill="x", pady=(0, 8))

    def _try_unlock(self):
        from ..crypto import verify_pin
        pin = self.pin_entry.get()
        if verify_pin(pin):
            self.on_unlock()
            self.destroy()
        else:
            self.error_lbl.config(text=t("wrongPin", self.lang))
            self.pin_entry.delete(0, tk.END)
