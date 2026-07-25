"""A pan-and-zoom canvas with explicit world coordinates."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from .image_viewer import _wheel_direction

Bounds = tuple[float, float, float, float]


class WorldCanvas(tk.Canvas):
    """Draw application data in a stable 2D world coordinate system.

    Override :meth:`draw_world` and create items with the ``"world"`` tag.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        y_up: bool = True,
        initial_scale: float = 1.0,
        min_scale: float = 0.01,
        max_scale: float = 10_000.0,
        zoom_step: float = 1.15,
        pan_button: int = 1,
        background: str = "#ffffff",
        **canvas_options: Any,
    ) -> None:
        if initial_scale <= 0:
            raise ValueError("initial_scale must be positive")
        if min_scale <= 0 or max_scale < min_scale or zoom_step <= 1:
            raise ValueError("invalid scale limits")
        if pan_button not in {1, 2, 3}:
            raise ValueError("pan_button must be 1, 2, or 3")

        super().__init__(
            master,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            **canvas_options,
        )
        self.y_up = y_up
        self.initial_scale = initial_scale
        self.min_scale = min_scale
        self.max_scale = max_scale
        self.zoom_step = zoom_step
        self.pan_button = pan_button
        self.view_scale = initial_scale
        self.origin_x = 0.0
        self.origin_y = 0.0
        self.world_bounds: Bounds | None = None
        self._drag_start: tuple[int, int] | None = None
        self._drag_origin: tuple[float, float] | None = None
        self._last_canvas_size = (1, 1)

        self.bind("<Configure>", self._on_configure)
        self.bind(
            f"<ButtonPress-{pan_button}>",
            self._on_pan_start,
            add="+",
        )
        self.bind(
            f"<B{pan_button}-Motion>",
            self._on_pan_move,
            add="+",
        )
        self.bind(
            f"<ButtonRelease-{pan_button}>",
            self._on_pan_end,
            add="+",
        )
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)
        self.bind("<Button-5>", self._on_mousewheel)
        self.bind("<Double-Button-1>", lambda _event: self.reset_view(), add="+")

    def world_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        """Transform world coordinates to canvas pixels."""

        canvas_x = self.origin_x + x * self.view_scale
        direction = -1.0 if self.y_up else 1.0
        canvas_y = self.origin_y + direction * y * self.view_scale
        return canvas_x, canvas_y

    def canvas_to_world(self, x: float, y: float) -> tuple[float, float]:
        """Transform canvas pixels to world coordinates."""

        world_x = (x - self.origin_x) / self.view_scale
        direction = -1.0 if self.y_up else 1.0
        world_y = direction * (y - self.origin_y) / self.view_scale
        return world_x, world_y

    def set_view(
        self,
        center: tuple[float, float],
        scale: float,
    ) -> None:
        """Set the world point at the center and pixels-per-world-unit scale."""

        if scale <= 0:
            raise ValueError("scale must be positive")
        self.view_scale = min(max(scale, self.min_scale), self.max_scale)
        canvas_width, canvas_height = self._canvas_size()
        world_x, world_y = center
        self.origin_x = canvas_width / 2 - world_x * self.view_scale
        direction = -1.0 if self.y_up else 1.0
        self.origin_y = (
            canvas_height / 2 - direction * world_y * self.view_scale
        )
        self.redraw()

    def set_world_bounds(self, bounds: Bounds, *, fit: bool = False) -> None:
        """Remember reset bounds and optionally fit them immediately."""

        _validate_bounds(bounds)
        self.world_bounds = bounds
        if fit:
            self.fit_bounds(bounds)

    def fit_bounds(self, bounds: Bounds, *, padding: float = 20.0) -> None:
        """Fit a world rectangle inside the current canvas."""

        _validate_bounds(bounds)
        if padding < 0:
            raise ValueError("padding must be non-negative")
        minimum_x, minimum_y, maximum_x, maximum_y = bounds
        world_width = max(maximum_x - minimum_x, 1e-12)
        world_height = max(maximum_y - minimum_y, 1e-12)
        canvas_width, canvas_height = self._canvas_size()
        available_width = max(canvas_width - 2 * padding, 1.0)
        available_height = max(canvas_height - 2 * padding, 1.0)
        scale = min(
            available_width / world_width,
            available_height / world_height,
        )
        self.set_view(
            (
                (minimum_x + maximum_x) / 2,
                (minimum_y + maximum_y) / 2,
            ),
            scale,
        )

    def reset_view(self) -> None:
        """Fit remembered bounds, or center the origin at the initial scale."""

        if self.world_bounds is not None:
            self.fit_bounds(self.world_bounds)
        else:
            self.set_view((0.0, 0.0), self.initial_scale)

    def zoom_at(self, canvas_x: float, canvas_y: float, factor: float) -> None:
        """Zoom around a canvas position without moving its world point."""

        if factor <= 0:
            raise ValueError("factor must be positive")
        world_x, world_y = self.canvas_to_world(canvas_x, canvas_y)
        self.view_scale = min(
            max(self.view_scale * factor, self.min_scale),
            self.max_scale,
        )
        self.origin_x = canvas_x - world_x * self.view_scale
        direction = -1.0 if self.y_up else 1.0
        self.origin_y = canvas_y - direction * world_y * self.view_scale
        self.redraw()

    def pan_by(self, delta_x: float, delta_y: float) -> None:
        """Pan by canvas pixels."""

        self.origin_x += delta_x
        self.origin_y += delta_y
        self.redraw()

    def find_at(
        self,
        canvas_x: float,
        canvas_y: float,
        *,
        radius: float = 3.0,
    ) -> tuple[int, ...]:
        """Return canvas item IDs under or near a point."""

        if radius < 0:
            raise ValueError("radius must be non-negative")
        return self.find_overlapping(
            canvas_x - radius,
            canvas_y - radius,
            canvas_x + radius,
            canvas_y + radius,
        )

    def redraw(self) -> None:
        """Clear world-tagged items and invoke :meth:`draw_world`."""

        self.delete("world")
        self.draw_world()

    def draw_world(self) -> None:
        """Draw application items using the ``"world"`` tag."""

    def _on_configure(self, event: tk.Event) -> None:
        old_width, old_height = self._last_canvas_size
        self.origin_x += (event.width - old_width) / 2
        self.origin_y += (event.height - old_height) / 2
        self._last_canvas_size = (event.width, event.height)
        self.redraw()

    def _on_pan_start(self, event: tk.Event) -> None:
        self._drag_start = (event.x, event.y)
        self._drag_origin = (self.origin_x, self.origin_y)
        self.configure(cursor="fleur")

    def _on_pan_move(self, event: tk.Event) -> None:
        if self._drag_start is None or self._drag_origin is None:
            return
        self.origin_x = self._drag_origin[0] + event.x - self._drag_start[0]
        self.origin_y = self._drag_origin[1] + event.y - self._drag_start[1]
        self.redraw()

    def _on_pan_end(self, _event: tk.Event) -> None:
        self._drag_start = None
        self._drag_origin = None
        self.configure(cursor="")

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        direction = _wheel_direction(event)
        if direction == 0:
            return None
        factor = self.zoom_step if direction > 0 else 1 / self.zoom_step
        self.zoom_at(event.x, event.y, factor)
        return "break"

    def _canvas_size(self) -> tuple[int, int]:
        return max(self.winfo_width(), 1), max(self.winfo_height(), 1)


def _validate_bounds(bounds: Bounds) -> None:
    minimum_x, minimum_y, maximum_x, maximum_y = bounds
    if maximum_x < minimum_x or maximum_y < minimum_y:
        raise ValueError("bounds must be ordered as min_x, min_y, max_x, max_y")
