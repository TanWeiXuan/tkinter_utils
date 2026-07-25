"""Small scheduling helpers built on tkinter's event loop."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass
import tkinter as tk
from typing import Any


@dataclass
class _PendingCall:
    after_id: str
    callback: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class TkDebouncer:
    """Coalesce delayed callbacks by key.

    Methods must be called from the tkinter thread. Calling :meth:`call` again
    with the same key replaces the earlier pending callback.
    """

    def __init__(self, master: tk.Misc) -> None:
        self.master = master
        self._pending: dict[Hashable, _PendingCall] = {}
        self._closed = False
        master.bind("<Destroy>", self._on_destroy, add="+")

    def call(
        self,
        key: Hashable,
        delay_ms: int,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Schedule ``callback``, replacing a pending call with the same key."""

        if self._closed:
            raise RuntimeError("TkDebouncer is closed")
        if delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")
        self.cancel(key)
        after_id = self.master.after(
            delay_ms,
            lambda: self._invoke(key),
        )
        self._pending[key] = _PendingCall(after_id, callback, args, kwargs)

    def pending(self, key: Hashable) -> bool:
        """Return whether ``key`` has a callback waiting to run."""

        return key in self._pending

    def cancel(self, key: Hashable) -> bool:
        """Cancel one pending callback and report whether it existed."""

        pending = self._pending.pop(key, None)
        if pending is None:
            return False
        try:
            self.master.after_cancel(pending.after_id)
        except tk.TclError:
            pass
        return True

    def flush(self, key: Hashable) -> bool:
        """Run one pending callback immediately."""

        pending = self._pending.pop(key, None)
        if pending is None:
            return False
        try:
            self.master.after_cancel(pending.after_id)
        except tk.TclError:
            pass
        pending.callback(*pending.args, **pending.kwargs)
        return True

    def cancel_all(self) -> None:
        """Cancel every pending callback."""

        for key in list(self._pending):
            self.cancel(key)

    def close(self) -> None:
        """Cancel pending callbacks and reject future scheduling."""

        if self._closed:
            return
        self.cancel_all()
        self._closed = True

    def _invoke(self, key: Hashable) -> None:
        pending = self._pending.pop(key, None)
        if pending is not None and not self._closed:
            pending.callback(*pending.args, **pending.kwargs)

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self.master:
            self.close()
