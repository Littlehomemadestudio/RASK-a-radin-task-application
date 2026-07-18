"""
rask.ui.widgets.scrollable
==========================

Scrollable containers:

  * ``SmoothScrollFrame(ctk.CTkScrollableFrame)`` — mouse-wheel acceleration
  * ``VirtualList(ctk.CTkScrollableFrame)`` — virtualised list (only renders
    visible items)
  * ``ParallaxHeader(ctk.CTkFrame)`` — header that shrinks on scroll
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from . import theme as _theme

__all__ = ["SmoothScrollFrame", "VirtualList", "ParallaxHeader"]


# =============================================================================
# === SmoothScrollFrame                                                     ===
# =============================================================================

class SmoothScrollFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame with smoother mouse-wheel scrolling.

    Adds acceleration: the first wheel event scrolls a small amount,
    and consecutive events within 200ms add momentum.
    """

    def __init__(
        self,
        master: Any = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._last_scroll_time: float = 0.0
        self._velocity: float = 0.0
        self._anim_job = None
        try:
            # Bind mouse wheel on the inner canvas
            self._parent_canvas.bind("<MouseWheel>", self._on_wheel, add="+")
            self._parent_canvas.bind("<Button-4>", self._on_wheel_linux, add="+")
            self._parent_canvas.bind("<Button-5>", self._on_wheel_linux, add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_wheel(self, evt: Any) -> None:
        try:
            import time
            now = time.time()
            delta = -evt.delta / 120.0
            # Acceleration: consecutive events increase velocity
            if now - self._last_scroll_time < 0.2:
                self._velocity += delta * 2
            else:
                self._velocity = delta * 2
            self._last_scroll_time = now
            # Cap velocity
            self._velocity = helpers.clamp(self._velocity, -30, 30)
            self._apply_scroll()
        except Exception:
            pass

    def _on_wheel_linux(self, evt: Any) -> None:
        try:
            delta = -1 if evt.num == 5 else 1
            self._velocity += delta * 2
            self._velocity = helpers.clamp(self._velocity, -30, 30)
            self._apply_scroll()
        except Exception:
            pass

    def _apply_scroll(self) -> None:
        try:
            self._parent_canvas.yview_scroll(int(self._velocity), "units")
        except Exception:
            pass
        # Decay velocity
        self._velocity *= 0.85
        if abs(self._velocity) < 0.5:
            self._velocity = 0
            return
        if self._anim_job:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
        self._anim_job = self.after(16, self._apply_scroll)


# =============================================================================
# === VirtualList                                                           ===
# =============================================================================

class VirtualList(ctk.CTkScrollableFrame):
    """Virtualised list — only renders visible items.

    Suitable for very long lists (1000+ items) where creating one
    widget per item would be expensive.

    Provide a ``item_count`` and an ``item_factory`` callback that
    receives ``(parent_frame, index)`` and should populate the frame
    with the item's content.
    """

    def __init__(
        self,
        master: Any = None,
        item_count: int = 0,
        item_factory: Optional[Callable[[Any, int], Any]] = None,
        item_height: int = 64,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(master, **kwargs)
        self._item_count = item_count
        self._item_factory = item_factory
        self._item_height = item_height
        self._lang = lang
        self._rendered_indices: set[int] = set()
        self._item_widgets: dict[int, ctk.CTkFrame] = {}
        try:
            self._parent_canvas.bind("<MouseWheel>",
                                       lambda _e: self._render_visible(),
                                       add="+")
            self.bind("<Configure>",
                       lambda _e: self.after(50, self._render_visible),
                       add="+")
        except Exception:
            pass
        # Set the scrollregion to the full virtual height
        self.after(100, self._render_visible)

    def set_item_count(self, count: int) -> None:
        self._item_count = count
        # Clear existing
        for idx, w in list(self._item_widgets.items()):
            try:
                w.destroy()
            except Exception:
                pass
        self._item_widgets.clear()
        self._rendered_indices.clear()
        self._render_visible()

    def _render_visible(self) -> None:
        if self._item_factory is None:
            return
        try:
            self.update_idletasks()
            top = self._parent_canvas.canvasy(0)
            bottom = self._parent_canvas.canvasy(self.winfo_height())
            first = max(0, int(top // self._item_height) - 2)
            last = min(self._item_count,
                        int(bottom // self._item_height) + 3)
            # Destroy off-screen items
            for idx in list(self._item_widgets.keys()):
                if idx < first or idx >= last:
                    try:
                        self._item_widgets[idx].destroy()
                    except Exception:
                        pass
                    self._item_widgets.pop(idx, None)
                    self._rendered_indices.discard(idx)
            # Render visible items
            for idx in range(first, last):
                if idx in self._item_widgets:
                    continue
                frame = ctk.CTkFrame(self, fg_color="transparent",
                                      height=self._item_height)
                frame.grid(row=idx, column=0, sticky="ew", padx=4, pady=1)
                frame.grid_propagate(False)
                self._item_factory(frame, idx)
                self._item_widgets[idx] = frame
                self._rendered_indices.add(idx)
        except Exception:
            pass

    def refresh(self) -> None:
        """Force re-render of all visible items."""
        for idx, w in list(self._item_widgets.items()):
            try:
                w.destroy()
            except Exception:
                pass
        self._item_widgets.clear()
        self._rendered_indices.clear()
        self._render_visible()


# =============================================================================
# === ParallaxHeader                                                        ===
# =============================================================================

class ParallaxHeader(ctk.CTkFrame):
    """Header that shrinks when the scrollable frame below it is scrolled.

    Use :meth:`attach` to bind it to a scrollable frame's scroll events.
    """

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        collapsed_height: int = 56,
        expanded_height: int = 120,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("height", expanded_height)
        super().__init__(master, **kwargs)
        self._title = title
        self._collapsed_h = collapsed_height
        self._expanded_h = expanded_height
        self._lang = lang
        self._current_h = expanded_height
        self._scroll_frame: Optional[ctk.CTkScrollableFrame] = None
        from .headers import Header
        self._inner = Header(self, title=title, lang=lang)
        self._inner.pack(fill="both", expand=True)

    def attach(self, scroll_frame: ctk.CTkScrollableFrame) -> None:
        """Bind to a scroll frame's scroll events."""
        self._scroll_frame = scroll_frame
        try:
            scroll_frame._parent_canvas.bind("<MouseWheel>",
                                              self._on_scroll, add="+")
        except Exception:
            pass

    def _on_scroll(self, _evt: Any) -> None:
        if self._scroll_frame is None:
            return
        try:
            y = self._scroll_frame._parent_canvas.yview()[0]
            # y is in [0, 1] — 0 = top, 1 = bottom
            target_h = int(helpers.lerp(self._expanded_h,
                                          self._collapsed_h, y))
            if target_h != self._current_h:
                self.configure(height=target_h)
                self._current_h = target_h
        except Exception:
            pass


def _self_test() -> int:
    classes = [SmoothScrollFrame, VirtualList, ParallaxHeader]
    print(f"Scrollable module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
