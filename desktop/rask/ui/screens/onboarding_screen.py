"""
rask.ui.screens.onboarding_screen
=================================

3-slide onboarding flow shown to first-time users.

Mirrors ``web/index.html`` ``#onboarding`` and the corresponding JS
``showOnboarding`` / ``renderOnboarding`` / ``finishOnboarding``
functions in ``web/js/app.js``.

Slides (sourced from :data:`config.ONBOARDING_SLIDES`):
    1. ``"زمان را زیبا پیگیری کن"`` — ring icon, gold accent
    2. ``"هدف تعیین کن. زنجیره بساز."`` — flame icon, green accent
    3. ``"۱۰۰٪ آفلاین. خصوصی."`` — shield icon, info-blue accent

Each slide shows:
    * A large circular illustration with the slide's accent colour and
      icon glyph, with a glowing animated ring
    * The slide title (32pt bold gold, centred)
    * The slide body (15pt dim, centred, line-height 1.7)
    * 3 progress dots at the bottom — the active dot stretches into a
      24×8 gold pill

Controls:
    * ``Skip`` button (top-trailing corner) — calls ``on_complete``
      immediately
    * ``Previous`` button (only on slides 2-3) — moves back one slide
    * ``Next`` / ``Start`` button — advances; on slide 3, fires
      ``on_complete``

Slide transitions are 320ms ease-out fade-and-slide (matches
``config.ANIM_ONBOARDING_SLIDE``).
"""
from __future__ import annotations

import math
from typing import Any, Callable, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import helpers
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import GhostButton, GoldButton, TextButton

__all__ = ["OnboardingView"]


# =============================================================================
# === Slide illustration canvas                                              ===
# =============================================================================

class _Illustration(ctk.CTkCanvas):
    """Animated circular illustration for a single onboarding slide.

    Draws:
        * A glowing outer ring (gold halo, pulsing alpha)
        * The slide's accent-coloured border ring
        * An inner spinning arc (rotating 360° over 3 seconds)
        * The slide's icon glyph in the centre (drawn via Pillow when
          available, unicode fallback otherwise)
    """

    def __init__(
        self,
        master: Any,
        icon_name: str = "ring",
        accent: str = config.GOLD,
        size: int = 200,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("bg", config.MATTE_BLACK)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("borderwidth", 0)
        super().__init__(master, **kwargs)
        self._icon_name = icon_name
        self._accent = accent
        self._size = size
        self._lang = lang
        self._t0: float = 0.0
        self._job: Optional[Any] = None
        import time
        self._t0 = time.time() * 1000.0
        self.bind("<Configure>", lambda _e: self._redraw(), add="+")
        self._redraw()
        self._tick()

    def _tick(self) -> None:
        self._redraw()
        self._job = self.after(33, self._tick)

    def _redraw(self) -> None:
        try:
            self.delete("all")
            w = int(self.cget("width"))
            h = int(self.cget("height"))
            if w < 4 or h < 4:
                return
        except Exception:
            return
        import time
        t_ms = (time.time() * 1000.0) - self._t0
        cx, cy = w / 2.0, h / 2.0
        r_outer = min(w, h) / 2.0 - 12.0
        # Pulsing outer halo
        pulse = 0.5 + 0.5 * math.sin(t_ms / 800.0)
        halo_alpha = 0.15 + 0.18 * pulse
        halo_color = helpers.mix_colors(
            config.MATTE_BLACK, self._accent,
            max(0.0, min(1.0, halo_alpha)))
        try:
            for i in range(4):
                gr = r_outer + 6.0 + i * 5.0
                ga = max(0.0, halo_alpha * (1.0 - i / 4.0))
                gc = helpers.mix_colors(config.MATTE_BLACK, self._accent, ga)
                self.create_oval(cx - gr, cy - gr, cx + gr, cy + gr,
                                  fill=gc, outline="")
        except Exception:
            pass
        # Main ring (accent, 4px)
        try:
            self.create_oval(cx - r_outer, cy - r_outer,
                              cx + r_outer, cy + r_outer,
                              outline=self._accent, width=4)
        except Exception:
            pass
        # Inner spinning arc — rotates 360° over 3 seconds
        spin = (t_ms / 3000.0) % 1.0
        # Two arcs offset by 180°, both spanning ~110°
        for offset_deg in (0.0, 180.0):
            start = 90.0 - 360.0 * spin - offset_deg
            try:
                self.create_arc(
                    cx - r_outer + 18, cy - r_outer + 18,
                    cx + r_outer - 18, cy + r_outer - 18,
                    outline=self._accent, width=8,
                    style="arc", start=start, extent=110.0,
                )
            except Exception:
                pass
        # Inner soft fill
        try:
            inner_r = r_outer - 32.0
            self.create_oval(cx - inner_r, cy - inner_r,
                              cx + inner_r, cy + inner_r,
                              fill=helpers.mix_colors(
                                  config.MATTE_BLACK, self._accent, 0.06),
                              outline="")
        except Exception:
            pass
        # Centre glyph — try Pillow icon, fall back to unicode
        glyph_drawn = False
        try:
            img = _icons.icon(self._icon_name, int(r_outer * 0.8),
                              color=self._accent)
            if img is not None:
                # CTkImage can be placed on a canvas via create_image
                self.create_image(cx, cy, image=img)
                glyph_drawn = True
        except Exception:
            pass
        if not glyph_drawn:
            try:
                glyph = _icons.icon_glyph(self._icon_name)
                font = _theme.theme.font(
                    size=int(r_outer * 0.9), weight="normal", lang="en")
                self.create_text(cx, cy, text=glyph,
                                  fill=self._accent, font=font)
            except Exception:
                pass

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def destroy(self) -> None:  # type: ignore[override]
        self.stop()
        super().destroy()


# =============================================================================
# === OnboardingView                                                        ===
# =============================================================================

class OnboardingView(ctk.CTkFrame):
    """3-slide onboarding flow.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.
    lang
        ``"fa"`` (default) or ``"en"``.
    on_complete
        Callback invoked when the user taps ``Start`` (last slide) or
        ``Skip``.  The view does not mark itself as having onboarded —
        the caller is responsible for persisting that state (typically
        via ``settings_service.set_onboarded(True)``).
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        on_complete: Optional[Callable[[], Any]] = None,
        slides: Optional[List[dict]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._on_complete = on_complete
        # Slide definitions — default to config.ONBOARDING_SLIDES
        self._slides: List[dict] = list(
            slides if slides is not None else config.ONBOARDING_SLIDES)
        self._index: int = 0
        self._anim_job: Optional[Any] = None
        self._anim_t: float = 0.0
        self._build()
        self._render_slide(animate=False)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Lay out the onboarding view: top bar + slide + dots + buttons."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # top bar
        self.grid_rowconfigure(1, weight=1)  # slide content
        self.grid_rowconfigure(2, weight=0)  # dots
        self.grid_rowconfigure(3, weight=0)  # buttons

        rtl = i18n.is_rtl(self._lang)

        # --- Top bar: Skip button on the trailing side ---
        top_bar = ctk.CTkFrame(self, fg_color="transparent", height=48)
        top_bar.grid(row=0, column=0, sticky="ew", padx=config.SPACE_LG,
                      pady=config.SPACE_MD)
        top_bar.grid_columnconfigure(0, weight=1)
        self._skip_btn = TextButton(
            top_bar,
            text=i18n.t("skip", self._lang),
            command=self._on_skip,
            lang=self._lang,
            color=config.TEXT_DIM,
            hover_color=config.GOLD,
            height=36,
            font_size=config.FONT_SIZE_BODY,
        )
        # In RTL the trailing side is the left; in LTR it's the right.
        self._skip_btn.grid(row=0, column=0,
                             sticky="e" if rtl else "w")

        # --- Slide content area (illustration + title + body) ---
        self._slide_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._slide_frame.grid(row=1, column=0, sticky="nsew",
                                 padx=config.SPACE_XL, pady=config.SPACE_MD)
        self._slide_frame.grid_columnconfigure(0, weight=1)
        self._slide_frame.grid_rowconfigure(0, weight=0)  # illustration
        self._slide_frame.grid_rowconfigure(1, weight=0)  # title
        self._slide_frame.grid_rowconfigure(2, weight=1)  # body (expands)

        # Illustration canvas (created/destroyed on slide change)
        self._illustration: Optional[_Illustration] = None

        # Title
        self._title_label = ctk.CTkLabel(
            self._slide_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="center", justify="center",
            wraplength=440,
        )
        self._title_label.grid(row=1, column=0, sticky="ew",
                                 pady=(config.SPACE_LG, config.SPACE_SM))

        # Body
        self._body_label = ctk.CTkLabel(
            self._slide_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_DEFAULT,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="center", justify="center",
            wraplength=440,
        )
        self._body_label.grid(row=2, column=0, sticky="nsew",
                                pady=(config.SPACE_SM, config.SPACE_XL))

        # --- Progress dots ---
        dots_row = ctk.CTkFrame(self, fg_color="transparent", height=24)
        dots_row.grid(row=2, column=0, sticky="ew",
                        pady=(0, config.SPACE_MD))
        dots_row.grid_columnconfigure(0, weight=1)
        self._dots_frame = ctk.CTkFrame(dots_row, fg_color="transparent")
        self._dots_frame.grid(row=0, column=0)
        self._dots: List[ctk.CTkFrame] = []
        for i in range(len(self._slides)):
            d = ctk.CTkFrame(
                self._dots_frame, width=8, height=8,
                fg_color=config.TEXT_FAINT,
                corner_radius=config.RADIUS_PILL,
            )
            d.grid(row=0, column=i, padx=4, pady=8)
            self._dots.append(d)

        # --- Buttons (Previous + Next/Start) ---
        btn_row = ctk.CTkFrame(self, fg_color="transparent", height=52)
        btn_row.grid(row=3, column=0, sticky="ew",
                      padx=config.SPACE_XL, pady=(0, config.SPACE_XL))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        self._prev_btn = GhostButton(
            btn_row,
            text=i18n.t("previous", self._lang),
            command=self._on_prev,
            lang=self._lang, height=44,
            font_size=config.FONT_SIZE_DEFAULT,
        )
        # Previous is always trailing side in RTL/LTR
        prev_col = 0 if rtl else 1
        next_col = 1 if rtl else 0
        self._prev_btn.grid(row=0, column=prev_col, sticky="ew",
                              padx=(4, 4))

        self._next_btn = GoldButton(
            btn_row,
            text=i18n.t("next", self._lang),
            command=self._on_next,
            lang=self._lang, height=44,
            font_size=config.FONT_SIZE_DEFAULT,
        )
        self._next_btn.grid(row=0, column=next_col, sticky="ew",
                              padx=(4, 4))

    # ------------------------------------------------------------------
    # Slide rendering
    # ------------------------------------------------------------------
    def _render_slide(self, animate: bool = True) -> None:
        """Render the current slide.  ``animate=True`` plays a fade-in."""
        slide = self._slides[self._index]
        # Title + body — pulled from the slide dict by current language
        title_key = f"title_{self._lang}"
        body_key = f"body_{self._lang}"
        title = slide.get(title_key) or slide.get("title_fa") or ""
        body = slide.get(body_key) or slide.get("body_fa") or ""
        accent = slide.get("accent", config.GOLD)
        icon_name = slide.get("icon", "ring")

        # Rebuild illustration
        if self._illustration is not None:
            self._illustration.stop()
            self._illustration.destroy()
            self._illustration = None
        self._illustration = _Illustration(
            self._slide_frame, icon_name=icon_name, accent=accent,
            size=200, lang=self._lang,
        )
        self._illustration.grid(row=0, column=0, pady=(config.SPACE_XL,
                                                         config.SPACE_LG))

        # Update labels
        self._title_label.configure(text=title)
        self._body_label.configure(text=body)

        # Update dot indicators
        for i, d in enumerate(self._dots):
            if i == self._index:
                d.configure(width=24, fg_color=config.GOLD)
            else:
                d.configure(width=8, fg_color=config.TEXT_FAINT)

        # Update button labels + visibility
        is_last = (self._index == len(self._slides) - 1)
        is_first = (self._index == 0)
        if is_last:
            self._next_btn.configure(text=i18n.t("start", self._lang))
        else:
            self._next_btn.configure(text=i18n.t("next", self._lang))
        if is_first:
            self._prev_btn.grid_remove()
        else:
            self._prev_btn.grid()
            self._prev_btn.configure(text=i18n.t("previous", self._lang))

        # Trigger fade-in animation
        if animate:
            self._anim_t = 0.0
            self._run_fade_in()
        else:
            self._title_label.configure(text_color=config.GOLD)
            self._body_label.configure(text_color=config.TEXT_DIM)

    def _run_fade_in(self) -> None:
        """Animate a fade-in / slide-up on the title + body labels."""
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
        self._anim_t = 0.0
        self._anim_total = max(2, config.ANIM_ONBOARDING_SLIDE // 16)
        self._fade_tick()

    def _fade_tick(self) -> None:
        self._anim_t += 1
        t = self._anim_t / max(1, self._anim_total)
        t_eased = helpers.ease_out_cubic(t)
        title_color = helpers.mix_colors(config.MATTE_BLACK, config.GOLD,
                                          t_eased)
        body_color = helpers.mix_colors(config.MATTE_BLACK, config.TEXT_DIM,
                                         t_eased)
        try:
            self._title_label.configure(text_color=title_color)
            self._body_label.configure(text_color=body_color)
        except Exception:
            pass
        if self._anim_t < self._anim_total:
            self._anim_job = self.after(16, self._fade_tick)
        else:
            self._anim_job = None

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------
    def _on_skip(self) -> None:
        """Skip button — finish onboarding immediately."""
        self._fire_complete()

    def _on_prev(self) -> None:
        """Previous button — go back one slide."""
        if self._index > 0:
            self._index -= 1
            self._render_slide(animate=True)

    def _on_next(self) -> None:
        """Next / Start button — advance or finish."""
        if self._index >= len(self._slides) - 1:
            self._fire_complete()
        else:
            self._index += 1
            self._render_slide(animate=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def index(self) -> int:
        """Current slide index (0-based)."""
        return self._index

    def go_to_slide(self, index: int) -> None:
        """Jump directly to slide ``index`` (clamped to valid range)."""
        self._index = max(0, min(len(self._slides) - 1, int(index)))
        self._render_slide(animate=True)

    def refresh(self) -> None:
        """Re-render the current slide (called on language change)."""
        # Update button labels in case language changed
        self._skip_btn.configure(text=i18n.t("skip", self._lang))
        self._render_slide(animate=False)

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------
    def _fire_complete(self) -> None:
        """Invoke the on_complete callback exactly once."""
        if self._on_complete is None:
            return
        cb = self._on_complete
        self._on_complete = None  # one-shot
        try:
            cb()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def destroy(self) -> None:  # type: ignore[override]
        if self._illustration is not None:
            try:
                self._illustration.stop()
            except Exception:
                pass
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print(f"OnboardingView module: {len(config.ONBOARDING_SLIDES)} slides")
    print(f"  Slide 1: {config.ONBOARDING_SLIDES[0]['title_fa']}")
    print(f"  Slide 2: {config.ONBOARDING_SLIDES[1]['title_fa']}")
    print(f"  Slide 3: {config.ONBOARDING_SLIDES[2]['title_fa']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
