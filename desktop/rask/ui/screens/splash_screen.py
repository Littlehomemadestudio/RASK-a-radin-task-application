"""
rask.ui.screens.splash_screen
=============================

Animated full-screen splash view shown for ~2.2 seconds at app startup.

Mirrors ``web/index.html`` ``#splash`` element and ``styles.css``
``.splash`` / ``.splash-logo`` / ``.splash-title`` / ``.splash-tagline``
rules exactly:

* Matte-black full-screen background
* Centered 180×180 gold-bordered circular logo with the glyph ``"R"``
* Logo pulses (scale 1.0 → 1.05 → 1.0) on a 2-second sine cycle
* Subtle gold-dust particles drift upward in the background
* App name ``"رَسک"`` fades in below the logo (gold, 42pt bold)
* Tagline ``"زمان، ظریف."`` appears below the title (dim italic 13pt)
* A 3-dot loading indicator pulses at the bottom of the screen

After ``ANIM_SPLASH`` ms (default 2200) the view calls the
``on_complete`` callback so the app shell can transition to the
onboarding or lock screen.

The view is a :class:`ctk.CTkFrame` (not a Toplevel) so the app shell
can pack/grid it directly inside the main window.
"""
from __future__ import annotations

import math
import random
from typing import Any, Callable, List, Optional, Tuple

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

__all__ = ["SplashView"]


# =============================================================================
# === Gold-dust particle                                                     ===
# =============================================================================

class _Particle:
    """Internal particle struct for the gold-dust effect.

    Each particle has a position, a velocity, a size, an alpha, and a
    colour drawn from the gold palette.  Updated each tick by the
    splash canvas animation loop.
    """

    __slots__ = ("x", "y", "vx", "vy", "size", "alpha", "color", "life")

    def __init__(self, w: int, h: int) -> None:
        self.x: float = random.uniform(0.0, float(w))
        # Spawn somewhere in the bottom half so they drift up across
        # the logo.
        self.y: float = random.uniform(float(h) * 0.45, float(h))
        self.vx: float = random.uniform(-0.15, 0.15)
        self.vy: float = random.uniform(-0.7, -0.25)
        self.size: float = random.uniform(1.2, 3.0)
        self.alpha: float = random.uniform(0.18, 0.55)
        self.color: str = random.choice(
            (config.GOLD, config.GOLD_SOFT, config.GOLD_BRIGHT, config.GOLD_GLOW))
        self.life: int = random.randint(120, 320)

    def step(self, w: int, h: int) -> bool:
        """Advance the particle one tick.  Return False if it died."""
        self.x += self.vx
        self.y += self.vy
        self.vy *= 0.998  # gentle air resistance
        self.life -= 1
        # Fade out as life runs low
        if self.life < 60:
            self.alpha *= 0.96
        return self.life > 0 and self.y > -10


# =============================================================================
# === SplashView                                                            ===
# =============================================================================

class SplashView(ctk.CTkFrame):
    """Animated splash screen.

    Parameters
    ----------
    parent
        Parent widget (usually the app shell).
    app
        The main application object — kept for symmetry with the other
        screens but not used here.
    lang
        ``"fa"`` (default) or ``"en"``.
    on_complete
        Callback invoked once after the splash duration has elapsed.
        The splash does not destroy itself — the caller is responsible
        for hiding/replacing it (typically by switching to the
        onboarding or lock screen).
    duration_ms
        How long to show the splash before firing ``on_complete``.
        Defaults to :data:`config.ANIM_SPLASH` (2200 ms) to match the
        web ``setTimeout(..., 2200)`` exactly.
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        on_complete: Optional[Callable[[], Any]] = None,
        duration_ms: int = config.ANIM_SPLASH,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._on_complete = on_complete
        self._duration = int(duration_ms)
        self._start_time: float = 0.0
        self._completed: bool = False
        self._pulse_job: Optional[Any] = None
        self._particle_job: Optional[Any] = None
        self._complete_job: Optional[Any] = None
        self._dot_phase: int = 0
        self._particles: List[_Particle] = []
        self._build()
        self._start_animations()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Lay out the splash: canvas (background + logo) + labels + dots."""
        # Canvas fills the whole view — we draw the logo + particles on
        # it so we can animate scale/glow without rebuilding widgets.
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._canvas = ctk.CTkCanvas(
            self,
            bg=config.MATTE_BLACK,
            highlightthickness=0,
            borderwidth=0,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        # App-name label below the logo (drawn on the canvas, so we
        # can fade it in smoothly).
        # Loading dots at the very bottom of the canvas.
        try:
            self.bind("<Configure>", self._on_resize, add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Animations
    # ------------------------------------------------------------------
    def _start_animations(self) -> None:
        """Kick off the pulse, particle, and complete-timer loops."""
        import time
        self._start_time = time.time() * 1000.0
        # Initial redraw
        self._redraw_canvas()
        # Pulse loop (16ms ≈ 60 FPS)
        self._pulse_job = self.after(16, self._tick_pulse)
        # Particle loop (33ms ≈ 30 FPS — particles are slow)
        self._particle_job = self.after(33, self._tick_particles)
        # Loading dots (400ms per phase)
        self._dot_job = self.after(400, self._tick_dots)  # type: ignore[attr-defined]
        # Fire on_complete after the configured duration
        self._complete_job = self.after(self._duration, self._fire_complete)

    def _on_resize(self, _evt: Any = None) -> None:
        """Re-draw on window resize."""
        self._redraw_canvas()

    def _tick_pulse(self) -> None:
        """Pulse the logo scale + ring glow on a 2-second cycle."""
        self._redraw_canvas()
        self._pulse_job = self.after(33, self._tick_pulse)

    def _tick_particles(self) -> None:
        """Advance + redraw particles."""
        try:
            w = max(1, self.winfo_width())
            h = max(1, self.winfo_height())
        except Exception:
            w, h = 540, 900
        # Spawn new particles up to a cap
        if len(self._particles) < 40 and random.random() < 0.45:
            self._particles.append(_Particle(w, h))
        # Step + cull
        self._particles = [p for p in self._particles if p.step(w, h)]
        self._particle_job = self.after(33, self._tick_particles)

    def _tick_dots(self) -> None:
        """Cycle the loading-dot phase."""
        self._dot_phase = (self._dot_phase + 1) % 3
        self._dot_job = self.after(400, self._tick_dots)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _redraw_canvas(self) -> None:
        """Repaint the entire splash canvas."""
        try:
            self._canvas.delete("all")
            w = max(1, self.winfo_width())
            h = max(1, self.winfo_height())
        except Exception:
            return
        # --- Particles (drawn first so logo is on top) -----------------
        for p in self._particles:
            try:
                # Approximate alpha by mixing with the bg colour
                col = helpers.mix_colors(config.MATTE_BLACK, p.color,
                                          max(0.0, min(1.0, p.alpha)))
                self._canvas.create_oval(
                    p.x - p.size, p.y - p.size,
                    p.x + p.size, p.y + p.size,
                    fill=col, outline="",
                )
            except Exception:
                pass
        # --- Logo circle (pulsing) -------------------------------------
        import time
        t_ms = (time.time() * 1000.0) - self._start_time
        # Pulse: 2-second cycle, scale 1.0 → 1.05 → 1.0
        phase = (t_ms % 2000.0) / 2000.0
        scale = 1.0 + 0.05 * math.sin(phase * 2.0 * math.pi)
        base_size = 180.0
        size = base_size * scale
        cx, cy = w / 2.0, h / 2.0 - 60.0
        r = size / 2.0
        # Outer glow (gold halo, varying intensity)
        glow_alpha = 0.25 + 0.20 * (0.5 + 0.5 * math.sin(phase * 2.0 * math.pi))
        glow_color = helpers.mix_colors(config.MATTE_BLACK, config.GOLD,
                                         max(0.0, min(1.0, glow_alpha)))
        for i in range(6):
            gr = r + 6.0 + i * 4.0
            ga = max(0.0, glow_alpha * (1.0 - i / 6.0))
            gc = helpers.mix_colors(config.MATTE_BLACK, config.GOLD, ga)
            try:
                self._canvas.create_oval(cx - gr, cy - gr, cx + gr, cy + gr,
                                          fill=gc, outline="")
            except Exception:
                pass
        # Ring (gold border, 4px)
        try:
            self._canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline=config.GOLD, width=4,
            )
        except Exception:
            pass
        # Inner fill (subtle dark surface)
        try:
            self._canvas.create_oval(
                cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4,
                outline=config.GOLD_DIM, width=1,
            )
        except Exception:
            pass
        # Glyph "R" in the centre
        try:
            font = _theme.theme.font(
                size=int(size * 0.55), weight="bold", lang="en")
            self._canvas.create_text(
                cx, cy, text="R", fill=config.GOLD, font=font,
            )
        except Exception:
            pass
        # --- App name (fade in 600..1400 ms) ---------------------------
        fade_t = (t_ms - 600.0) / 800.0
        fade_t = max(0.0, min(1.0, fade_t))
        # Offset slightly for the slide-up feel
        title_y = cy + r + 50.0 + (1.0 - fade_t) * 12.0
        try:
            title_color = helpers.mix_colors(config.MATTE_BLACK, config.GOLD,
                                              fade_t)
            font = _theme.theme.font(
                size=config.FONT_SIZE_HEADING_LG, weight="bold",
                lang=self._lang)
            self._canvas.create_text(
                cx, title_y,
                text=i18n.t("appName", self._lang),
                fill=title_color, font=font,
            )
        except Exception:
            pass
        # --- Tagline (fade in 900..1700 ms) ----------------------------
        tag_t = (t_ms - 900.0) / 800.0
        tag_t = max(0.0, min(1.0, tag_t))
        tag_y = title_y + 32.0 + (1.0 - tag_t) * 8.0
        try:
            tag_color = helpers.mix_colors(config.MATTE_BLACK,
                                            config.TEXT_DIM, tag_t)
            font = _theme.theme.font(
                size=config.FONT_SIZE_BODY, weight="normal",
                lang=self._lang)
            self._canvas.create_text(
                cx, tag_y,
                text=i18n.t("tagline", self._lang),
                fill=tag_color, font=font,
            )
        except Exception:
            pass
        # --- Loading dots at the bottom --------------------------------
        dot_y = h - 60.0
        dot_cx = w / 2.0
        for i in range(3):
            active = (i == self._dot_phase)
            radius = 4.0 if active else 2.5
            color = config.GOLD if active else config.TEXT_FAINT
            try:
                self._canvas.create_oval(
                    dot_cx - 18.0 + i * 18.0 - radius,
                    dot_y - radius,
                    dot_cx - 18.0 + i * 18.0 + radius,
                    dot_y + radius,
                    fill=color, outline="",
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------
    def _fire_complete(self) -> None:
        """Invoke the on_complete callback exactly once."""
        if self._completed:
            return
        self._completed = True
        # Final fade-out frame: paint over with full opacity (the
        # caller will destroy/hide us).
        try:
            self._canvas.delete("all")
        except Exception:
            pass
        if self._on_complete:
            try:
                self._on_complete()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Cancel all animation loops.  Safe to call multiple times."""
        for attr in ("_pulse_job", "_particle_job", "_dot_job",
                     "_complete_job"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)
        self._particles.clear()

    def refresh(self) -> None:
        """No-op for API consistency with other screens.

        The splash view is purely animated and doesn't show data, so
        there's nothing to refresh.  Provided so the app shell can
        call ``refresh()`` on any screen uniformly.
        """
        pass

    def destroy(self) -> None:  # type: ignore[override]
        """Override to ensure animation loops are cancelled first."""
        self.stop()
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print(f"SplashView module: class registered, lang default 'fa'.")
    print(f"  Duration default: {config.ANIM_SPLASH}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
