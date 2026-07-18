"""
rask.ui.widgets.confetti
========================

Celebration confetti overlay — used for badge unlocks and goal achievements.

  * ``Confetti`` — fullscreen overlay with falling gold particles
  * ``Confetti.celebrate(parent, duration=2000)`` — convenience class method

Particles are gold / gold-soft / gold-bright coloured, fall with gravity,
and fade out.  Up to ~80 particles per burst for performance.
"""
from __future__ import annotations

import math
import random
from typing import Any, List, Optional, Tuple

import customtkinter as ctk

from ... import config
from ...core import helpers
from . import theme as _theme

__all__ = ["Confetti"]


# =============================================================================
# === Particle                                                              ===
# =============================================================================

class _Particle:
    """One confetti particle with position, velocity, colour, rotation."""

    __slots__ = ("x", "y", "vx", "vy", "color", "size", "rot", "vrot",
                  "alpha", "shape")

    def __init__(self, x: float, y: float, color: str) -> None:
        self.x = x
        self.y = y
        # Initial upward velocity + spread
        angle = random.uniform(-math.pi * 0.8, -math.pi * 0.2)
        speed = random.uniform(8, 18)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.color = color
        self.size = random.uniform(4, 9)
        self.rot = random.uniform(0, math.pi * 2)
        self.vrot = random.uniform(-0.3, 0.3)
        self.alpha = 1.0
        self.shape = random.choice(("rect", "circle", "tri"))


# =============================================================================
# === Confetti                                                              ===
# =============================================================================

class Confetti(ctk.CTkToplevel):
    """Fullscreen overlay with falling gold confetti.

    Use the class method :meth:`celebrate` rather than constructing
    directly.
    """

    PALETTE: Tuple[str, ...] = (config.GOLD, config.GOLD_SOFT,
                                  config.GOLD_BRIGHT, config.GOLD_GLOW)

    def __init__(
        self,
        master: Any = None,
        duration: int = 2000,
        particle_count: int = 80,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("bg", config.MATTE_BLACK)
        super().__init__(master, **kwargs)
        self._duration = duration
        self._particle_count = particle_count
        self._particles: List[_Particle] = []
        self._canvas: Optional[ctk.CTkCanvas] = None
        self._job = None
        self._start_time = 0.0
        # Make the window cover the whole parent
        try:
            self.overrideredirect(True)
            self.attributes("-topmost", True)
            try:
                self.attributes("-alpha", 0.95)
                self.attributes("-transparentcolor", config.MATTE_BLACK)
            except Exception:
                pass
            if master is not None:
                master.update_idletasks()
                x = master.winfo_rootx()
                y = master.winfo_rooty()
                w = master.winfo_width()
                h = master.winfo_height()
                self.geometry(f"{w}x{h}+{x}+{y}")
            else:
                self.geometry("540x900")
        except Exception:
            pass
        self._build_canvas()
        self._spawn_particles()
        self._start_time = self._now()
        # Bind to close on click
        try:
            self.bind("<Button-1>", lambda _e: self._finish(), add="+")
            self.bind("<Escape>", lambda _e: self._finish(), add="+")
        except Exception:
            pass
        # Start animation loop
        self._tick_anim()

    def _now(self) -> float:
        import time
        return time.time() * 1000.0

    def _build_canvas(self) -> None:
        try:
            self._canvas = ctk.CTkCanvas(self,
                                          bg=config.MATTE_BLACK,
                                          highlightthickness=0,
                                          borderwidth=0)
            self._canvas.pack(fill="both", expand=True)
            # Make canvas click-transparent
            try:
                self._canvas.configure(state="disabled")
            except Exception:
                pass
        except Exception:
            pass

    def _spawn_particles(self) -> None:
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            if w < 10:
                w = 540
            if h < 10:
                h = 900
            # Spawn at top centre
            cx = w / 2
            cy = h * 0.3
            for _ in range(self._particle_count):
                color = random.choice(self.PALETTE)
                x = cx + random.uniform(-w * 0.2, w * 0.2)
                y = cy + random.uniform(-20, 20)
                self._particles.append(_Particle(x, y, color))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _tick_anim(self) -> None:
        try:
            elapsed = self._now() - self._start_time
            if elapsed > self._duration:
                self._finish()
                return
            # Clear canvas
            self._canvas.delete("all")
            # Update + draw each particle
            w = self.winfo_width() or 540
            h = self.winfo_height() or 900
            gravity = 0.6
            for p in self._particles:
                # Physics
                p.vy += gravity
                p.vx *= 0.99
                p.x += p.vx
                p.y += p.vy
                p.rot += p.vrot
                # Fade out in the last 500ms
                if elapsed > self._duration - 500:
                    p.alpha = max(0.0, 1.0 - (elapsed - (self._duration - 500)) / 500)
                # Cull off-screen
                if p.y > h + 20:
                    p.alpha = 0.0
                # Draw shape
                self._draw_particle(p)
        except Exception:
            pass
        self._job = self.after(16, self._tick_anim)

    def _draw_particle(self, p: _Particle) -> None:
        if p.alpha <= 0.0 or self._canvas is None:
            return
        try:
            color = p.color
            if p.alpha < 1.0:
                # Mix toward background to simulate alpha
                color = helpers.mix_colors(color, config.MATTE_BLACK,
                                            1.0 - p.alpha)
            if p.shape == "rect":
                # Rotated rectangle approximation
                cos_r = math.cos(p.rot)
                sin_r = math.sin(p.rot)
                hw = p.size
                hh = p.size / 2
                pts = []
                for sx, sy in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
                    rx = p.x + sx * cos_r - sy * sin_r
                    ry = p.y + sx * sin_r + sy * cos_r
                    pts.append((rx, ry))
                self._canvas.create_polygon(pts, fill=color, outline="")
            elif p.shape == "circle":
                self._canvas.create_oval(p.x - p.size, p.y - p.size,
                                          p.x + p.size, p.y + p.size,
                                          fill=color, outline="")
            else:  # tri
                cos_r = math.cos(p.rot)
                sin_r = math.sin(p.rot)
                pts = []
                for sx, sy in [(0, -p.size), (p.size, p.size),
                                 (-p.size, p.size)]:
                    rx = p.x + sx * cos_r - sy * sin_r
                    ry = p.y + sx * sin_r + sy * cos_r
                    pts.append((rx, ry))
                self._canvas.create_polygon(pts, fill=color, outline="")
        except Exception:
            pass

    def _finish(self) -> None:
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        try:
            self.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Class-method convenience API
    # ------------------------------------------------------------------
    @classmethod
    def celebrate(
        cls,
        parent: Any,
        duration: int = 2000,
        particle_count: int = 80,
    ) -> "Confetti":
        """Fire a gold-confetti burst over `parent` for `duration` ms."""
        try:
            return cls(parent, duration=duration,
                        particle_count=particle_count)
        except Exception:
            # Return a dummy so callers don't crash
            class _Dummy:
                def destroy(self) -> None:
                    pass
            return _Dummy()  # type: ignore[return-value]


def _self_test() -> int:
    classes = [Confetti]
    print(f"Confetti module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
