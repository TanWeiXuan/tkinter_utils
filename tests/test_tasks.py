from __future__ import annotations

import threading
import time
import tkinter as tk
import unittest

from tkinter_utils import BackgroundTaskRunner, TaskContext


def _spin_until(
    root: tk.Tk,
    predicate,
    *,
    timeout: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("timed out waiting for tkinter callback")
        root.update()
        time.sleep(0.005)
    root.update()


class BackgroundTaskRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError as exc:
            self.skipTest(f"tk display unavailable: {exc}")
        self.runner = BackgroundTaskRunner(self.root, poll_interval_ms=5)

    def tearDown(self) -> None:
        if hasattr(self, "runner"):
            self.runner.close(wait=True)
        if hasattr(self, "root"):
            self.root.destroy()

    def test_success_progress_and_callbacks_return_to_tk_thread(self) -> None:
        main_thread = threading.get_ident()
        progress: list[int] = []
        results: list[int] = []
        callback_threads: list[int] = []

        def worker(context: TaskContext[int]) -> int:
            context.report(1)
            context.report(2)
            return 42

        handle = self.runner.submit(
            worker,
            on_progress=lambda value: (
                progress.append(value),
                callback_threads.append(threading.get_ident()),
            ),
            on_success=lambda value: (
                results.append(value),
                callback_threads.append(threading.get_ident()),
            ),
        )
        _spin_until(self.root, lambda: handle.done)

        self.assertEqual(handle.state, "succeeded")
        self.assertEqual(handle.result, 42)
        self.assertEqual(progress[-1], 2)
        self.assertEqual(results, [42])
        self.assertTrue(callback_threads)
        self.assertEqual(set(callback_threads), {main_thread})

    def test_cancellation_suppresses_success(self) -> None:
        started = threading.Event()
        cancelled: list[bool] = []
        results: list[str] = []

        def worker(context: TaskContext[None]) -> str:
            started.set()
            while not context.cancelled:
                time.sleep(0.005)
            context.raise_if_cancelled()
            return "should not be delivered"

        handle = self.runner.submit(
            worker,
            on_success=results.append,
            on_cancelled=lambda: cancelled.append(True),
        )
        _spin_until(self.root, started.is_set)
        self.assertTrue(handle.cancel())
        _spin_until(self.root, lambda: handle.done)

        self.assertEqual(handle.state, "cancelled")
        self.assertEqual(results, [])
        self.assertEqual(cancelled, [True])

    def test_failure_is_delivered_and_done_runs_after_error(self) -> None:
        events: list[str] = []

        def worker(_context: TaskContext[None]) -> None:
            raise RuntimeError("sensor offline")

        handle = self.runner.submit(
            worker,
            on_error=lambda error: events.append(str(error)),
            on_done=lambda completed: events.append(completed.state),
        )
        _spin_until(self.root, lambda: handle.done)

        self.assertEqual(handle.state, "failed")
        self.assertIsInstance(handle.exception, RuntimeError)
        self.assertEqual(events, ["sensor offline", "failed"])


if __name__ == "__main__":
    unittest.main()
