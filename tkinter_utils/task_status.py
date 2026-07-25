"""A compact status and progress panel for long-running operations."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk
from typing import Any, Literal

StatusState = Literal["idle", "running", "succeeded", "failed", "cancelled"]


class TaskStatusPanel(ttk.Frame):
    """Present task state without owning task execution."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        idle_message: str = "Ready",
        **frame_options: Any,
    ) -> None:
        super().__init__(master, **frame_options)
        self.columnconfigure(0, weight=1)
        self.message_var = tk.StringVar(master=self, value=idle_message)
        self.detail_var = tk.StringVar(master=self, value="")
        self.state: StatusState = "idle"
        self._cancel_command: Callable[[], Any] | None = None

        self.message_label = ttk.Label(
            self,
            textvariable=self.message_var,
            anchor=tk.W,
        )
        self.message_label.grid(row=0, column=0, sticky=tk.EW)
        self.cancel_button = ttk.Button(
            self,
            text="Cancel",
            command=self._cancel,
        )
        self.cancel_button.grid(row=0, column=1, padx=(8, 0))
        self.cancel_button.grid_remove()

        self.progressbar = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progressbar.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(4, 0))
        self.detail_label = ttk.Label(
            self,
            textvariable=self.detail_var,
            anchor=tk.W,
        )
        self.detail_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky=tk.EW,
            pady=(3, 0),
        )
        self.detail_label.grid_remove()

    def start(
        self,
        message: str,
        *,
        total: float | None = None,
        cancel_command: Callable[[], Any] | None = None,
        detail: str = "",
    ) -> None:
        """Show a running determinate or indeterminate task."""

        if total is not None and total <= 0:
            raise ValueError("total must be positive")
        self._stop_progress()
        self.state = "running"
        self.message_var.set(message)
        self._set_detail(detail)
        self._cancel_command = cancel_command
        if cancel_command is None:
            self.cancel_button.grid_remove()
        else:
            self.cancel_button.state(["!disabled"])
            self.cancel_button.grid()

        if total is None:
            self.progressbar.configure(mode="indeterminate", maximum=100, value=0)
            self.progressbar.start(10)
        else:
            self.progressbar.configure(
                mode="determinate",
                maximum=total,
                value=0,
            )

    def update_progress(
        self,
        value: float | None = None,
        *,
        message: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Update a running task's value or labels."""

        if value is not None:
            self.progressbar.configure(value=value)
        if message is not None:
            self.message_var.set(message)
        if detail is not None:
            self._set_detail(detail)

    def complete(self, message: str = "Complete", *, detail: str = "") -> None:
        self._finish("succeeded", message, detail)

    def fail(self, message: str = "Failed", *, detail: str = "") -> None:
        self._finish("failed", message, detail)

    def cancelled(self, message: str = "Cancelled", *, detail: str = "") -> None:
        self._finish("cancelled", message, detail)

    def reset(self, message: str = "Ready") -> None:
        self._finish("idle", message, "")
        self.progressbar.configure(mode="determinate", maximum=100, value=0)

    def _finish(self, state: StatusState, message: str, detail: str) -> None:
        self._stop_progress()
        self.state = state
        self.message_var.set(message)
        self._set_detail(detail)
        self._cancel_command = None
        self.cancel_button.grid_remove()

    def _cancel(self) -> None:
        if self._cancel_command is None:
            return
        self.cancel_button.state(["disabled"])
        self.message_var.set("Cancelling…")
        self._cancel_command()

    def _stop_progress(self) -> None:
        self.progressbar.stop()

    def _set_detail(self, detail: str) -> None:
        self.detail_var.set(detail)
        if detail:
            self.detail_label.grid()
        else:
            self.detail_label.grid_remove()
