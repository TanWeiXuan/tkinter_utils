"""Run blocking work without blocking tkinter's event loop."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import queue
import threading
import tkinter as tk
from types import TracebackType
from typing import Any, Generic, Literal, TypeVar

ProgressT = TypeVar("ProgressT")
ResultT = TypeVar("ResultT")
TaskState = Literal["running", "succeeded", "failed", "cancelled"]
_MISSING = object()


class TaskCancelled(Exception):
    """Raised by cooperative workers when cancellation is requested."""


class TaskContext(Generic[ProgressT]):
    """Thread-safe progress and cancellation interface passed to a worker."""

    def __init__(
        self,
        cancel_event: threading.Event,
        report_callback: Callable[[ProgressT], None],
    ) -> None:
        self._cancel_event = cancel_event
        self._report_callback = report_callback

    @property
    def cancelled(self) -> bool:
        """Whether cancellation has been requested."""

        return self._cancel_event.is_set()

    @property
    def cancel_event(self) -> threading.Event:
        """The underlying event for APIs that accept ``threading.Event``."""

        return self._cancel_event

    def report(self, progress: ProgressT) -> None:
        """Publish progress; only the latest unconsumed value is retained."""

        if not self.cancelled:
            self._report_callback(progress)

    def raise_if_cancelled(self) -> None:
        """Stop a cooperative worker after a cancellation request."""

        if self.cancelled:
            raise TaskCancelled()


class TaskHandle(Generic[ProgressT, ResultT]):
    """Control and inspect one submitted background task."""

    def __init__(
        self,
        task_id: int,
        on_progress: Callable[[ProgressT], None] | None,
        on_success: Callable[[ResultT], None] | None,
        on_error: Callable[[BaseException], None] | None,
        on_cancelled: Callable[[], None] | None,
        on_done: Callable[[TaskHandle[ProgressT, ResultT]], None] | None,
    ) -> None:
        self.task_id = task_id
        self.state: TaskState = "running"
        self.result: ResultT | None = None
        self.exception: BaseException | None = None
        self._cancel_event = threading.Event()
        self._future: Future[ResultT] | None = None
        self._on_progress = on_progress
        self._on_success = on_success
        self._on_error = on_error
        self._on_cancelled = on_cancelled
        self._on_done = on_done

    @property
    def cancellation_requested(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def done(self) -> bool:
        return self.state != "running"

    def cancel(self) -> bool:
        """Request cooperative cancellation.

        Returns ``False`` only when the task was already finished.
        """

        if self.done:
            return False
        self._cancel_event.set()
        if self._future is not None:
            self._future.cancel()
        return True


class BackgroundTaskRunner:
    """Dispatch worker results and progress callbacks on the tkinter thread."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        max_workers: int = 1,
        poll_interval_ms: int = 25,
        thread_name_prefix: str = "tk-task",
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if poll_interval_ms < 1:
            raise ValueError("poll_interval_ms must be at least 1")

        self.master = master
        self.poll_interval_ms = poll_interval_ms
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._handles: dict[int, TaskHandle[Any, Any]] = {}
        self._completion_queue: queue.SimpleQueue[TaskHandle[Any, Any]] = (
            queue.SimpleQueue()
        )
        self._progress: dict[int, Any] = {}
        self._progress_lock = threading.Lock()
        self._next_task_id = 1
        self._poll_after_id: str | None = None
        self._closed = False
        master.bind("<Destroy>", self._on_destroy, add="+")

    @property
    def active_tasks(self) -> tuple[TaskHandle[Any, Any], ...]:
        """A snapshot of unfinished task handles."""

        return tuple(self._handles.values())

    def submit(
        self,
        worker: Callable[..., ResultT],
        *worker_args: Any,
        on_progress: Callable[[ProgressT], None] | None = None,
        on_success: Callable[[ResultT], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
        on_done: Callable[[TaskHandle[ProgressT, ResultT]], None] | None = None,
        **worker_kwargs: Any,
    ) -> TaskHandle[ProgressT, ResultT]:
        """Submit ``worker`` and return a cancellation handle.

        The worker runs on a background thread and receives a
        :class:`TaskContext` followed by ``worker_args`` and ``worker_kwargs``.
        Every callback runs later on the tkinter thread.
        """

        if self._closed:
            raise RuntimeError("BackgroundTaskRunner is closed")

        task_id = self._next_task_id
        self._next_task_id += 1
        handle: TaskHandle[ProgressT, ResultT] = TaskHandle(
            task_id,
            on_progress,
            on_success,
            on_error,
            on_cancelled,
            on_done,
        )
        self._handles[task_id] = handle
        context = TaskContext(
            handle._cancel_event,
            lambda value: self._store_progress(task_id, value),
        )
        future = self._executor.submit(
            self._run_worker,
            worker,
            context,
            worker_args,
            worker_kwargs,
        )
        handle._future = future
        future.add_done_callback(
            lambda _future: self._completion_queue.put(handle)
        )
        self._ensure_polling()
        return handle

    def cancel_all(self) -> None:
        """Request cancellation for every active task."""

        for handle in self.active_tasks:
            handle.cancel()

    def close(self, *, wait: bool = False, cancel: bool = True) -> None:
        """Stop polling and shut down worker threads."""

        if self._closed:
            return
        self._closed = True
        if cancel:
            self.cancel_all()
        if self._poll_after_id is not None:
            try:
                self.master.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None
        self._executor.shutdown(wait=wait, cancel_futures=cancel)

    @staticmethod
    def _run_worker(
        worker: Callable[..., ResultT],
        context: TaskContext[ProgressT],
        worker_args: tuple[Any, ...],
        worker_kwargs: dict[str, Any],
    ) -> ResultT:
        context.raise_if_cancelled()
        result = worker(context, *worker_args, **worker_kwargs)
        context.raise_if_cancelled()
        return result

    def _store_progress(self, task_id: int, value: Any) -> None:
        with self._progress_lock:
            self._progress[task_id] = value

    def _ensure_polling(self) -> None:
        if self._poll_after_id is None:
            self._poll_after_id = self.master.after(
                self.poll_interval_ms,
                self._poll,
            )

    def _poll(self) -> None:
        self._poll_after_id = None
        if self._closed:
            return

        with self._progress_lock:
            progress = self._progress
            self._progress = {}
        for task_id, value in progress.items():
            handle = self._handles.get(task_id)
            if (
                handle is not None
                and not handle.cancellation_requested
                and handle._on_progress is not None
            ):
                self._invoke_callback(handle._on_progress, value)

        while True:
            try:
                handle = self._completion_queue.get_nowait()
            except queue.Empty:
                break
            self._finish(handle)

        if self._handles:
            self._ensure_polling()

    def _finish(self, handle: TaskHandle[Any, Any]) -> None:
        if self._handles.pop(handle.task_id, None) is None:
            return
        with self._progress_lock:
            final_progress = self._progress.pop(handle.task_id, _MISSING)
        if (
            final_progress is not _MISSING
            and not handle.cancellation_requested
            and handle._on_progress is not None
        ):
            self._invoke_callback(handle._on_progress, final_progress)

        future = handle._future
        try:
            if future is None:
                raise RuntimeError("task has no future")
            result = future.result()
        except (CancelledError, TaskCancelled):
            handle.state = "cancelled"
            if handle._on_cancelled is not None:
                self._invoke_callback(handle._on_cancelled)
        except BaseException as exc:
            if handle.cancellation_requested:
                handle.state = "cancelled"
                if handle._on_cancelled is not None:
                    self._invoke_callback(handle._on_cancelled)
            else:
                handle.state = "failed"
                handle.exception = exc
                if handle._on_error is not None:
                    self._invoke_callback(handle._on_error, exc)
        else:
            if handle.cancellation_requested:
                handle.state = "cancelled"
                if handle._on_cancelled is not None:
                    self._invoke_callback(handle._on_cancelled)
            else:
                handle.state = "succeeded"
                handle.result = result
                if handle._on_success is not None:
                    self._invoke_callback(handle._on_success, result)

        if handle._on_done is not None:
            self._invoke_callback(handle._on_done, handle)

    def _invoke_callback(self, callback: Callable[..., Any], *args: Any) -> None:
        try:
            callback(*args)
        except BaseException as exc:
            traceback: TracebackType | None = exc.__traceback__
            self.master.report_callback_exception(type(exc), exc, traceback)

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self.master:
            self.close(wait=False, cancel=True)
