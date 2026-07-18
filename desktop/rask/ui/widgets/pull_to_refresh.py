"""
rask.ui.widgets.pull_to_refresh
===============================

Pull-to-refresh indicator that wraps a scrollable frame.

  * ``PullToRefresh`` — wrapper that shows a gold spinner when the user
    pulls down beyond a threshold, then invokes the refresh callback.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from . import theme as _theme
from . import icons as _icons

__all__ = ["PullToRefresh"]


# =============================================================================
# === PullToRefresh                                                         ===
# =============================================================================

class PullToRefresh(ctk.CTkFrame):
    """Wrap a scrollable frame with a pull-to-refresh indicator.

    Parameters
    ----------
    scrollable
        The CTkScrollableFrame to attach to.
    on_refresh
        Callback invoked when the user pulls down past the threshold
        and releases.  Should return ``True`` to dismiss the spinner
        immediately or ``None`` to keep it spinning until
        :meth:`finish_refresh` is called.
    threshold
        Pull distance in pixels required to trigger a refresh.
    """

    def __init__(
        self,
        master: Any = None,
        scrollable: Optional[ctk.CTkScrollableFrame] = None,
        on_refresh: Optional[Callable[[], Any]] = None,
        threshold: int = 80,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._scrollable = scrollable
        self._on_refresh = on_refresh
        self._threshold = threshold
        self._lang = lang
        self._pulling = False
        self._pull_dist = 0
        self._refreshing = False
        self._spinner_angle = 0
        self._spinner_job = None
        # Build spinner
        self._spinner = ctk.CTkCanvas(self, width=32, height=32,
                                       bg=config.MATTE_BLACK,
                                       highlightthickness=0, borderwidth=0)
        self._spinner.create_arc(4, 4, 28, 28, start=90, extent=270,
                                  outline=config.GOLD, width=3,
                                  style="arc", tags="arc")
        # Hide spinner initially
        self._spinner.place_forget()
        # Bind to scrollable's canvas
        if scrollable is not None:
            try:
                canvas = scrollable._parent_canvas
                canvas.bind("<ButtonPress-1>", self._on_press, add="+")
                canvas.bind("<B1-Motion>", self._on_motion, add="+")
                canvas.bind("<ButtonRelease-1>", self._on_release, add="+")
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _on_press(self, evt: Any) -> None:
        try:
            # Only start pulling if at top of scroll
            if self._scrollable is None:
                return
            yview = self._scrollable._parent_canvas.yview()
            if yview[0] <= 0.001:
                self._pulling = True
                self._pull_start_y = evt.y
                self._pull_dist = 0
        except Exception:
            pass

    def _on_motion(self, evt: Any) -> None:
        if not self._pulling or self._refreshing:
            return
        try:
            dy = evt.y - getattr(self, "_pull_start_y", evt.y)
            if dy > 0:
                self._pull_dist = min(dy, self._threshold * 1.5)
                self._show_spinner(self._pull_dist)
        except Exception:
            pass

    def _on_release(self, _evt: Any) -> None:
        if not self._pulling:
            return
        self._pulling = False
        if self._pull_dist >= self._threshold:
            self._start_refresh()
        else:
            self._hide_spinner()

    def _show_spinner(self, dist: float) -> None:
        try:
            t = helpers.clamp(dist / self._threshold, 0, 1)
            # Spinner appears above the scrollable content
            self._spinner.place(relx=0.5, y=-32 + int(dist), anchor="n")
            # Rotate the arc to indicate pull progress
            angle = int(270 * t)
            self._spinner.itemconfig("arc", extent=angle)
        except Exception:
            pass

    def _hide_spinner(self) -> None:
        try:
            self._spinner.place_forget()
        except Exception:
            pass
        self._pull_dist = 0

    def _start_refresh(self) -> None:
        self._refreshing = True
        try:
            self._spinner.place(relx=0.5, y=8, anchor="n")
            self._spinner.itemconfig("arc", extent=270)
            self._spin_loop()
        except Exception:
            pass
        if self._on_refresh:
            try:
                result = self._on_refresh()
                if result:
                    self.finish_refresh()
            except Exception:
                self.finish_refresh()
        else:
            # No callback — auto-finish after 1 second
            self.after(1000, self.finish_refresh)

    def _spin_loop(self) -> None:
        if not self._refreshing:
            return
        try:
            self._spinner_angle = (self._spinner_angle + 10) % 360
            self._spinner.itemconfig("arc", start=90 - self._spinner_angle)
        except Exception:
            pass
        self._spinner_job = self.after(30, self._spin_loop)

    def finish_refresh(self) -> None:
        """Call this to dismiss the spinner after async refresh completes."""
        self._refreshing = False
        if self._spinner_job:
            try:
                self.after_cancel(self._spinner_job)
            except Exception:
                pass
            self._spinner_job = None
        self._hide_spinner()

    # ------------------------------------------------------------------
    @classmethod
    def attach(
        cls,
        scrollable: ctk.CTkScrollableFrame,
        on_refresh: Callable[[], Any],
        threshold: int = 80,
        lang: str = "fa",
    ) -> "PullToRefresh":
        """Convenience: attach a pull-to-refresh to an existing scrollable."""
        try:
            parent = scrollable.master
            p2r = cls(parent, scrollable=scrollable, on_refresh=on_refresh,
                       threshold=threshold, lang=lang)
            return p2r
        except Exception:
            # Return a no-op instance
            return cls()


def _self_test() -> int:
    classes = [PullToRefresh]
    print(f"Pull-to-refresh module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
