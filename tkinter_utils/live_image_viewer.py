"""A latest-frame image viewer for camera and sensor streams."""

from __future__ import annotations

from collections import deque
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

from .image_viewer import ImageViewer, _pillow


class LiveImageViewer(ImageViewer):
    """Display frames submitted from any thread without building a backlog."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        poll_interval_ms: int = 15,
        stale_after_s: float = 1.0,
        show_status: bool = True,
        **viewer_options: Any,
    ) -> None:
        if poll_interval_ms < 1:
            raise ValueError("poll_interval_ms must be at least 1")
        if stale_after_s <= 0:
            raise ValueError("stale_after_s must be positive")
        super().__init__(master, **viewer_options)
        self.poll_interval_ms = poll_interval_ms
        self.stale_after_s = stale_after_s
        self.show_status = show_status
        self.status_var = tk.StringVar(master=self, value="Waiting for frames")
        self.status_label = ttk.Label(
            self,
            textvariable=self.status_var,
            anchor=tk.W,
        )
        if show_status:
            self.status_label.grid(row=1, column=0, sticky=tk.EW, pady=(3, 0))

        self._pending_lock = threading.Lock()
        self._pending_frame: tuple[Any, float] | None = None
        self._display_times: deque[float] = deque()
        self._last_frame_time: float | None = None
        self._poll_after_id: str | None = None
        self.frames_received = 0
        self.frames_displayed = 0
        self.frames_dropped = 0
        self._running = False
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.start()

    @property
    def fps(self) -> float:
        """Recent displayed frame rate over a two-second window."""

        self._prune_display_times(time.monotonic())
        if len(self._display_times) < 2:
            return 0.0
        elapsed = self._display_times[-1] - self._display_times[0]
        return (len(self._display_times) - 1) / elapsed if elapsed > 0 else 0.0

    @property
    def running(self) -> bool:
        return self._running

    def submit_frame(self, image: Any, *, captured_at: float | None = None) -> None:
        """Submit a Pillow image from any thread.

        ``captured_at`` uses the :func:`time.monotonic` clock when supplied.
        Any unconsumed frame is replaced and counted as dropped.
        """

        Image, _ImageTk = _pillow()
        if not isinstance(image, Image.Image):
            raise TypeError("image must be a PIL.Image.Image")
        copied = image.copy()
        timestamp = time.monotonic() if captured_at is None else captured_at
        with self._pending_lock:
            self.frames_received += 1
            if self._pending_frame is not None:
                self.frames_dropped += 1
            self._pending_frame = (copied, timestamp)

    def start(self) -> None:
        """Start consuming submitted frames."""

        if self._running:
            return
        self._running = True
        self._schedule_poll()

    def stop(self) -> None:
        """Pause consumption while retaining the latest pending frame."""

        self._running = False
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None

    def reset_stats(self) -> None:
        self.frames_received = 0
        self.frames_displayed = 0
        self.frames_dropped = 0
        self._display_times.clear()
        self._update_status()

    def _schedule_poll(self) -> None:
        if self._running and self._poll_after_id is None:
            self._poll_after_id = self.after(
                self.poll_interval_ms,
                self._poll_frame,
            )

    def _poll_frame(self) -> None:
        self._poll_after_id = None
        if not self._running:
            return
        with self._pending_lock:
            pending = self._pending_frame
            self._pending_frame = None
        if pending is not None:
            image, captured_at = pending
            self.set_image(image, reset_view=False)
            now = time.monotonic()
            self.frames_displayed += 1
            self._last_frame_time = captured_at
            self._display_times.append(now)
            self._prune_display_times(now)
        self._update_status()
        self._schedule_poll()

    def _update_status(self) -> None:
        now = time.monotonic()
        if self._last_frame_time is None:
            state = "waiting"
        elif now - self._last_frame_time > self.stale_after_s:
            state = "stale"
        else:
            state = "live"
        self.status_var.set(
            f"{self.fps:.1f} FPS · {self.frames_dropped} dropped · {state}"
        )

    def _prune_display_times(self, now: float) -> None:
        cutoff = now - 2.0
        while self._display_times and self._display_times[0] < cutoff:
            self._display_times.popleft()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            self.stop()
