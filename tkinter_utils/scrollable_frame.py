"""A vertically scrollable ttk frame."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


class ScrollableFrame(ttk.Frame):
    """A frame whose ``content`` child scrolls vertically.

    Add application widgets to :attr:`content`, then place the
    ``ScrollableFrame`` itself with ``grid`` or ``pack``.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        height: int | None = None,
        padding: int | tuple[int, ...] = 0,
        canvas_background: str | None = None,
        **frame_options: Any,
    ) -> None:
        super().__init__(master, **frame_options)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        if canvas_background is None:
            canvas_background = ttk.Style(self).lookup("TFrame", "background")

        self.canvas = tk.Canvas(
            self,
            background=canvas_background,
            borderwidth=0,
            highlightthickness=0,
            height=height,
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        self.scrollbar.grid(row=0, column=1, sticky=tk.NS)

        self.content = ttk.Frame(self.canvas, padding=padding)
        self.content.columnconfigure(0, weight=1)
        # ``inner`` eases migration from an earlier implementation used by
        # some of the source projects.
        self.inner = self.content
        self._window_id = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor=tk.NW,
        )

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self._wheel_bindings: list[tuple[str, str]] = []
        self._install_mousewheel_bindings()
        self.bind("<Destroy>", self._on_destroy, add="+")

    def refresh(self) -> None:
        """Recalculate the scrollable area after programmatic content changes."""

        bounds = self.canvas.bbox("all")
        self.canvas.configure(scrollregion=bounds or (0, 0, 0, 0))

    def scroll_to_top(self) -> None:
        """Move the viewport to the first row."""

        self.canvas.yview_moveto(0.0)

    def _on_content_configure(self, _event: tk.Event) -> None:
        self.refresh()

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window_id, width=event.width)
        self.refresh()

    def _install_mousewheel_bindings(self) -> None:
        top_level = self.winfo_toplevel()
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            binding_id = top_level.bind(
                sequence,
                self._on_mousewheel,
                add="+",
            )
            if binding_id:
                self._wheel_bindings.append((sequence, binding_id))

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        top_level = self.winfo_toplevel()
        for sequence, binding_id in self._wheel_bindings:
            top_level.unbind(sequence, binding_id)
        self._wheel_bindings.clear()

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        if _nearest_scrollable_frame(event.widget) is not self:
            return None

        units = _mousewheel_units(event)
        if units == 0:
            return None

        before = self.canvas.yview()
        self.canvas.yview_scroll(units, "units")
        if self.canvas.yview() == before:
            return None
        return "break"


def _nearest_scrollable_frame(widget: tk.Misc) -> ScrollableFrame | None:
    current: tk.Misc | None = widget
    while current is not None:
        if isinstance(current, ScrollableFrame):
            return current
        current = getattr(current, "master", None)
    return None


def _mousewheel_units(event: tk.Event) -> int:
    """Translate Windows, macOS, and X11 wheel events to tkinter units."""

    button_number = getattr(event, "num", None)
    if button_number == 4:
        return -3
    if button_number == 5:
        return 3

    delta = int(getattr(event, "delta", 0))
    if delta == 0:
        return 0
    if abs(delta) >= 120:
        return -int(delta / 120)
    return -1 if delta > 0 else 1
