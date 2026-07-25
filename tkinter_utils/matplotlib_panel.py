"""Optional Matplotlib embedding for tkinter."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


class MatplotlibPanel(ttk.Frame):
    """Embed a Matplotlib figure, axes, canvas, and optional toolbar."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        figure: Any | None = None,
        toolbar: bool = True,
        projection: str | None = None,
        figure_options: dict[str, Any] | None = None,
        **frame_options: Any,
    ) -> None:
        Figure, FigureCanvasTkAgg, NavigationToolbar2Tk = _matplotlib()
        super().__init__(master, **frame_options)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        if figure is None:
            self.figure = Figure(**(figure_options or {}))
            self.axes = self.figure.add_subplot(111, projection=projection)
        else:
            if figure_options:
                raise ValueError(
                    "figure_options cannot be used with an existing figure"
                )
            if projection is not None:
                raise ValueError("projection cannot be used with an existing figure")
            self.figure = figure
            self.axes = figure.axes[0] if figure.axes else None

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky=tk.NSEW)
        self.toolbar: Any | None = None
        if toolbar:
            self.toolbar = NavigationToolbar2Tk(
                self.canvas,
                self,
                pack_toolbar=False,
            )
            self.toolbar.update()
            self.toolbar.grid(row=1, column=0, sticky=tk.EW)

    def draw_idle(self) -> None:
        self.canvas.draw_idle()

    def connect(self, event_name: str, callback: Any) -> int:
        """Connect a Matplotlib event and return its connection ID."""

        return self.canvas.mpl_connect(event_name, callback)

    def disconnect(self, connection_id: int) -> None:
        self.canvas.mpl_disconnect(connection_id)


def _matplotlib() -> tuple[Any, Any, Any]:
    try:
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg,
            NavigationToolbar2Tk,
        )
        from matplotlib.figure import Figure
    except ImportError as exc:
        raise RuntimeError(
            "MatplotlibPanel requires Matplotlib; install tkinter-utils[plots]"
        ) from exc
    return Figure, FigureCanvasTkAgg, NavigationToolbar2Tk
