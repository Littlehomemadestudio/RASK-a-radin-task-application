"""
rask.ui.widgets.skeleton
========================

Loading skeleton placeholders with a shimmer animation.

  * ``Skeleton``       — single rectangular shimmer block
  * ``SkeletonCard``   — card-shaped skeleton (avatar + 2 text lines)
  * ``SkeletonList``   — list of skeleton cards inside a scroll frame
"""
from __future__ import annotations

from typing import Any, List, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from . import theme as _theme

__all__ = ["Skeleton", "SkeletonCard", "SkeletonList"]


# =============================================================================
# === Skeleton                                                              ===
# =============================================================================

class Skeleton(ctk.CTkFrame):
    """Animated shimmer placeholder rectangle.

    Parameters
    ----------
    width, height
        Block dimensions.
    radius
        Corner radius.
    shimmer
        If True (default), animate a sweeping light wave across the block.
    """

    def __init__(
        self,
        master: Any = None,
        width: int = 200,
        height: int = 16,
        radius: int = config.RADIUS_SM,
        shimmer: bool = True,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE_HI)
        kwargs.setdefault("corner_radius", radius)
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._width = width
        self._height = height
        self._shimmer = shimmer
        self._shimmer_label: Optional[ctk.CTkLabel] = None
        self._shimmer_job = None
        self._shimmer_step = 0
        self._shimmer_total = max(2, config.ANIM_SLOW // 16)
        if shimmer:
            self._start_shimmer()

    def _start_shimmer(self) -> None:
        try:
            self._shimmer_label = ctk.CTkLabel(
                self, text="",
                fg_color="transparent",
            )
            self._shimmer_label.place(x=0, y=0, relwidth=1.0, relheight=1.0)
            self._tick_shimmer()
        except Exception:
            pass

    def _tick_shimmer(self) -> None:
        self._shimmer_step += 1
        if self._shimmer_step > self._shimmer_total:
            self._shimmer_step = 0
        t = self._shimmer_step / self._shimmer_total
        # Cycle through a brightness wave
        brightness = 0.5 + 0.5 * (1 - 2 * abs(t - 0.5))
        color = helpers.mix_colors(config.SURFACE_HI, config.SURFACE_HIGHER,
                                    brightness)
        try:
            self.configure(fg_color=color)
        except Exception:
            pass
        self._shimmer_job = self.after(16, self._tick_shimmer)

    def stop_shimmer(self) -> None:
        if self._shimmer_job:
            try:
                self.after_cancel(self._shimmer_job)
            except Exception:
                pass
            self._shimmer_job = None


# =============================================================================
# === SkeletonCard                                                          ===
# =============================================================================

class SkeletonCard(ctk.CTkFrame):
    """Card-shaped skeleton with avatar + 2 text lines."""

    def __init__(
        self,
        master: Any = None,
        width: int = 380,
        height: int = 80,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.DIVIDER)
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        # Avatar skeleton (circle)
        self._avatar = Skeleton(self, width=44, height=44,
                                 radius=22)
        self._avatar.pack(side="left", padx=12, pady=12)
        # Text lines
        text_col = ctk.CTkFrame(self, fg_color="transparent")
        text_col.pack(side="left", fill="both", expand=True,
                       padx=(0, 12), pady=12)
        self._line1 = Skeleton(text_col, width=200, height=14)
        self._line1.pack(anchor="w", pady=(0, 8))
        self._line2 = Skeleton(text_col, width=120, height=10)
        self._line2.pack(anchor="w")

    def stop_shimmer(self) -> None:
        for child in (self._avatar, self._line1, self._line2):
            try:
                child.stop_shimmer()  # type: ignore[attr-defined]
            except Exception:
                pass


# =============================================================================
# === SkeletonList                                                          ===
# =============================================================================

class SkeletonList(ctk.CTkScrollableFrame):
    """Scrollable list of :class:`SkeletonCard` items."""

    def __init__(
        self,
        master: Any = None,
        item_count: int = 6,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._items: List[SkeletonCard] = []
        self._item_count = item_count
        self._build()

    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._items = []
        for _ in range(self._item_count):
            card = SkeletonCard(self)
            card.pack(fill="x", padx=12, pady=4)
            self._items.append(card)

    def set_count(self, n: int) -> None:
        self._item_count = n
        self._build()

    def stop_shimmer(self) -> None:
        for item in self._items:
            try:
                item.stop_shimmer()
            except Exception:
                pass


def _self_test() -> int:
    classes = [Skeleton, SkeletonCard, SkeletonList]
    print(f"Skeleton module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
