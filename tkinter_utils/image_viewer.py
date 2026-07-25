"""A lightweight pan-and-zoom image viewer for tkinter."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any


class ImageViewer(ttk.Frame):
    """Display a Pillow image with fit-to-window, pan, and cursor zoom.

    Pillow is imported only when an image is loaded, so applications that use
    the other components do not need to install it.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        background: str = "#202020",
        placeholder: str = "No image",
        allow_upscale: bool = False,
        min_zoom: float = 0.05,
        max_zoom: float = 20.0,
        zoom_step: float = 1.15,
        **frame_options: Any,
    ) -> None:
        if min_zoom <= 0 or max_zoom < min_zoom or zoom_step <= 1:
            raise ValueError("invalid zoom limits")

        super().__init__(master, **frame_options)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self,
            background=background,
            borderwidth=0,
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)

        self.placeholder = placeholder
        self.allow_upscale = allow_upscale
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
        self.zoom_step = zoom_step

        self._image: Any | None = None
        self._photo: Any | None = None
        self._fit_scale = 1.0
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._drag_start: tuple[int, int] | None = None
        self._drag_origin: tuple[float, float] | None = None
        self._reset_after_id: str | None = None

        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_pan_end)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.canvas.bind("<Double-Button-1>", lambda _event: self.reset_view())
        self.clear()

    @property
    def image(self) -> Any | None:
        """The copied Pillow image currently displayed, if any."""

        return self._image

    @property
    def scale(self) -> float:
        """The current image-to-canvas scale."""

        return max(self._fit_scale * self._zoom, 0.001)

    def load(self, path: str | Path) -> None:
        """Load an image file using Pillow."""

        Image, _ImageTk = _pillow()
        with Image.open(path) as opened:
            self.set_image(opened)

    def set_image(self, image: Any, *, reset_view: bool = True) -> None:
        """Display a Pillow ``Image`` object.

        A private copy is retained so callers may safely close or mutate their
        source image. Set ``reset_view=False`` to preserve the viewport when
        replacing an image with another image of the same dimensions.
        """

        Image, _ImageTk = _pillow()
        if not isinstance(image, Image.Image):
            raise TypeError("image must be a PIL.Image.Image")
        previous_size = self._image.size if self._image is not None else None
        self._image = image.copy()
        if reset_view or previous_size != self._image.size:
            self._zoom = 1.0
            if self._reset_after_id is not None:
                self.after_cancel(self._reset_after_id)
            self._reset_after_id = self.after_idle(self.reset_view)
        else:
            self._render()

    def clear(self, placeholder: str | None = None) -> None:
        """Remove the image and show placeholder text."""

        if placeholder is not None:
            self.placeholder = placeholder
        self._image = None
        self._photo = None
        self.canvas.delete("all")
        self._draw_placeholder()

    def reset_view(self) -> None:
        """Fit and center the image in the current canvas."""

        self._reset_after_id = None
        if self._image is None:
            return
        self._zoom = 1.0
        self._fit_scale = _fit_scale(
            self._image.size,
            self._canvas_size(),
            self.allow_upscale,
        )
        display_width, display_height = self._display_size()
        canvas_width, canvas_height = self._canvas_size()
        self._offset_x = (canvas_width - display_width) / 2
        self._offset_y = (canvas_height - display_height) / 2
        self._render()

    def zoom_in(self) -> None:
        """Zoom one step around the center of the viewer."""

        self._zoom_at(
            self.canvas.winfo_width() / 2,
            self.canvas.winfo_height() / 2,
            self.zoom_step,
        )

    def zoom_out(self) -> None:
        """Zoom out one step around the center of the viewer."""

        self._zoom_at(
            self.canvas.winfo_width() / 2,
            self.canvas.winfo_height() / 2,
            1 / self.zoom_step,
        )

    def canvas_to_image(self, x: float, y: float) -> tuple[float, float]:
        """Convert canvas coordinates to source-image coordinates."""

        return (x - self._offset_x) / self.scale, (y - self._offset_y) / self.scale

    def image_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        """Convert source-image coordinates to canvas coordinates."""

        return self._offset_x + x * self.scale, self._offset_y + y * self.scale

    def draw_overlay(self, canvas: tk.Canvas) -> None:
        """Draw application overlays after the image.

        Subclasses may override this hook and use :meth:`image_to_canvas` to
        position canvas items. The default implementation draws nothing.
        """

    def _draw_placeholder(self) -> None:
        width, height = self._canvas_size()
        self.canvas.create_text(
            width / 2,
            height / 2,
            text=self.placeholder,
            fill="#a0a0a0",
            tags=("placeholder",),
        )

    def _on_canvas_configure(self, _event: tk.Event) -> None:
        if self._image is None:
            self.canvas.delete("placeholder")
            self._draw_placeholder()
            return

        old_scale = self.scale
        old_center = self.canvas_to_image(
            self.canvas.winfo_width() / 2,
            self.canvas.winfo_height() / 2,
        )
        self._fit_scale = _fit_scale(
            self._image.size,
            self._canvas_size(),
            self.allow_upscale,
        )
        canvas_width, canvas_height = self._canvas_size()
        self._offset_x = canvas_width / 2 - old_center[0] * self.scale
        self._offset_y = canvas_height / 2 - old_center[1] * self.scale
        if old_scale > 0:
            self._render()

    def _on_pan_start(self, event: tk.Event) -> None:
        if self._image is None:
            return
        self._drag_start = (event.x, event.y)
        self._drag_origin = (self._offset_x, self._offset_y)
        self.canvas.configure(cursor="fleur")

    def _on_pan_move(self, event: tk.Event) -> None:
        if (
            self._image is None
            or self._drag_start is None
            or self._drag_origin is None
        ):
            return
        self._offset_x = self._drag_origin[0] + event.x - self._drag_start[0]
        self._offset_y = self._drag_origin[1] + event.y - self._drag_start[1]
        self._render()

    def _on_pan_end(self, _event: tk.Event) -> None:
        self._drag_start = None
        self._drag_origin = None
        self.canvas.configure(cursor="")

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        direction = _wheel_direction(event)
        if self._image is None or direction == 0:
            return None
        factor = self.zoom_step if direction > 0 else 1 / self.zoom_step
        self._zoom_at(event.x, event.y, factor)
        return "break"

    def _zoom_at(self, canvas_x: float, canvas_y: float, factor: float) -> None:
        if self._image is None:
            return
        image_x, image_y = self.canvas_to_image(canvas_x, canvas_y)
        self._zoom = min(max(self._zoom * factor, self.min_zoom), self.max_zoom)
        self._offset_x = canvas_x - image_x * self.scale
        self._offset_y = canvas_y - image_y * self.scale
        self._render()

    def _render(self) -> None:
        if self._image is None:
            return
        Image, ImageTk = _pillow()
        self._clamp_offsets()
        display_size = self._display_size()
        resized = self._image.resize(display_size, Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(resized, master=self.canvas)
        self.canvas.delete("all")
        self.canvas.create_image(
            round(self._offset_x),
            round(self._offset_y),
            image=self._photo,
            anchor=tk.NW,
            tags=("image",),
        )
        self.draw_overlay(self.canvas)

    def _display_size(self) -> tuple[int, int]:
        if self._image is None:
            return (1, 1)
        width, height = self._image.size
        return (
            max(round(width * self.scale), 1),
            max(round(height * self.scale), 1),
        )

    def _canvas_size(self) -> tuple[int, int]:
        return max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)

    def _clamp_offsets(self) -> None:
        display_size = self._display_size()
        canvas_size = self._canvas_size()
        self._offset_x, self._offset_y = _clamp_offsets(
            (self._offset_x, self._offset_y),
            display_size,
            canvas_size,
        )


def _pillow() -> tuple[Any, Any]:
    try:
        from PIL import Image, ImageTk
    except ImportError as exc:
        raise RuntimeError(
            "ImageViewer requires Pillow; install tkinter-utils[images]"
        ) from exc
    return Image, ImageTk


def _fit_scale(
    image_size: tuple[int, int],
    canvas_size: tuple[int, int],
    allow_upscale: bool,
) -> float:
    image_width, image_height = image_size
    canvas_width, canvas_height = canvas_size
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    scale = min(canvas_width / image_width, canvas_height / image_height)
    if not allow_upscale:
        scale = min(scale, 1.0)
    return max(scale, 0.001)


def _clamp_offsets(
    offsets: tuple[float, float],
    display_size: tuple[int, int],
    canvas_size: tuple[int, int],
) -> tuple[float, float]:
    offset_x, offset_y = offsets
    display_width, display_height = display_size
    canvas_width, canvas_height = canvas_size

    if display_width <= canvas_width:
        offset_x = (canvas_width - display_width) / 2
    else:
        offset_x = min(0.0, max(offset_x, canvas_width - display_width))

    if display_height <= canvas_height:
        offset_y = (canvas_height - display_height) / 2
    else:
        offset_y = min(0.0, max(offset_y, canvas_height - display_height))
    return offset_x, offset_y


def _wheel_direction(event: tk.Event) -> int:
    button_number = getattr(event, "num", None)
    if button_number == 4:
        return 1
    if button_number == 5:
        return -1
    delta = int(getattr(event, "delta", 0))
    return (delta > 0) - (delta < 0)
