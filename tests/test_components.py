from __future__ import annotations

import time
import tkinter as tk
import unittest

from tkinter_utils import (
    ColumnSpec,
    DataTable,
    LiveImageViewer,
    MatplotlibPanel,
    TaskStatusPanel,
    TkDebouncer,
    ValidatedEntry,
    WorldCanvas,
)


class TkTestCase(unittest.TestCase):
    root: tk.Tk

    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
            self.root.geometry("420x320")
        except tk.TclError as exc:
            self.skipTest(f"tk display unavailable: {exc}")

    def tearDown(self) -> None:
        if hasattr(self, "root"):
            self.root.destroy()


class TkDebouncerTests(TkTestCase):
    def test_replaces_flushes_and_cancels_by_key(self) -> None:
        calls: list[int] = []
        debouncer = TkDebouncer(self.root)
        debouncer.call("redraw", 10_000, calls.append, 1)
        debouncer.call("redraw", 10_000, calls.append, 2)

        self.assertTrue(debouncer.pending("redraw"))
        self.assertTrue(debouncer.flush("redraw"))
        self.assertEqual(calls, [2])
        debouncer.call("redraw", 10_000, calls.append, 3)
        self.assertTrue(debouncer.cancel("redraw"))
        self.assertFalse(debouncer.pending("redraw"))


class ValidatedEntryTests(TkTestCase):
    def test_parses_range_checks_and_sets_invalid_state(self) -> None:
        entry = ValidatedEntry(
            self.root,
            parser=int,
            min_value=1,
            max_value=10,
            name="Iterations",
        )
        entry.set_value(4)
        self.assertEqual(entry.get_value(), 4)
        self.assertTrue(entry.valid)

        entry.variable.set("0")
        self.assertFalse(entry.validate_value())
        self.assertTrue(entry.instate(["invalid"]))
        self.assertEqual(entry.error_message, "Iterations must be at least 1")

        text = ValidatedEntry(self.root, parser=str, name="Robot name")
        with self.assertRaisesRegex(ValueError, "Robot name is required"):
            text.get_value()


class DataTableTests(TkTestCase):
    def test_refresh_preserves_selection_and_sort_uses_raw_values(self) -> None:
        table = DataTable(
            self.root,
            [
                ColumnSpec("name", "Name"),
                ColumnSpec("value", "Value", formatter=lambda value: f"{value:.1f}"),
            ],
            row_key="id",
        )
        table.pack(fill="both", expand=True)
        table.set_rows(
            [
                {"id": 1, "name": "Beta", "value": 10.0},
                {"id": 2, "name": "Alpha", "value": 2.0},
            ]
        )
        iid_for_two = next(
            iid
            for iid in table.tree.get_children()
            if table.tree.item(iid, "values")[0] == "Alpha"
        )
        table.tree.selection_set(iid_for_two)
        table.sort_by("value")
        first = table.tree.get_children()[0]
        self.assertEqual(table.tree.item(first, "values")[0], "Alpha")

        table.set_rows(
            [
                {"id": 1, "name": "Beta", "value": 11.0},
                {"id": 2, "name": "Alpha", "value": 3.0},
            ]
        )
        self.assertEqual(table.selected_keys(), [2])
        self.assertEqual(table.selected_rows()[0]["value"], 3.0)

        with self.assertRaisesRegex(ValueError, "duplicate row key"):
            table.set_rows(
                [
                    {"id": 1, "name": "One", "value": 1.0},
                    {"id": 1, "name": "Duplicate", "value": 2.0},
                ]
            )


class WorldCanvasTests(TkTestCase):
    def test_transform_round_trip_and_cursor_zoom(self) -> None:
        canvas = WorldCanvas(self.root, y_up=True)
        canvas.pack(fill="both", expand=True)
        self.root.update()
        canvas.set_view((10.0, 5.0), 4.0)

        center = (canvas.winfo_width() / 2, canvas.winfo_height() / 2)
        self.assertAlmostEqual(canvas.world_to_canvas(10.0, 5.0)[0], center[0])
        self.assertAlmostEqual(canvas.world_to_canvas(10.0, 5.0)[1], center[1])
        world_before = canvas.canvas_to_world(100, 80)
        canvas.zoom_at(100, 80, 2.0)
        world_after = canvas.canvas_to_world(100, 80)
        self.assertAlmostEqual(world_before[0], world_after[0])
        self.assertAlmostEqual(world_before[1], world_after[1])

        canvas.set_world_bounds((-2, -1, 2, 1), fit=True)
        left, _middle = canvas.world_to_canvas(-2, 0)
        right, _middle = canvas.world_to_canvas(2, 0)
        self.assertGreaterEqual(left, 0)
        self.assertLessEqual(right, canvas.winfo_width())


class TaskStatusPanelTests(TkTestCase):
    def test_determinate_progress_and_cancel_command(self) -> None:
        cancelled: list[bool] = []
        panel = TaskStatusPanel(self.root)
        panel.pack(fill="x")
        panel.start(
            "Detecting",
            total=20,
            cancel_command=lambda: cancelled.append(True),
        )
        panel.update_progress(7, detail="Frame 7 of 20")

        self.assertEqual(panel.state, "running")
        self.assertEqual(float(panel.progressbar["value"]), 7)
        panel.cancel_button.invoke()
        self.assertEqual(cancelled, [True])
        self.assertEqual(panel.message_var.get(), "Cancelling…")
        panel.cancelled()
        self.assertEqual(panel.state, "cancelled")


class LiveImageViewerTests(TkTestCase):
    def test_keeps_only_latest_pending_frame(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")

        viewer = LiveImageViewer(self.root, poll_interval_ms=5)
        viewer.pack(fill="both", expand=True)
        self.root.update()
        viewer.submit_frame(Image.new("RGB", (20, 10), "red"))
        viewer.submit_frame(Image.new("RGB", (20, 10), "green"))
        viewer.submit_frame(Image.new("RGB", (20, 10), "blue"))

        for _attempt in range(20):
            self.root.update()
            if viewer.frames_displayed:
                break
            time.sleep(0.005)
        self.assertEqual(viewer.frames_received, 3)
        self.assertEqual(viewer.frames_dropped, 2)
        self.assertEqual(viewer.frames_displayed, 1)
        self.assertEqual(viewer.image.getpixel((0, 0)), (0, 0, 255))


class MatplotlibPanelTests(TkTestCase):
    def test_creates_axes_and_draws_without_eager_pyplot_state(self) -> None:
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("Matplotlib is not installed")

        panel = MatplotlibPanel(self.root, toolbar=False)
        panel.pack(fill="both", expand=True)
        panel.axes.plot([0, 1], [0, 1])
        panel.draw_idle()
        self.root.update()
        self.assertEqual(len(panel.axes.lines), 1)


if __name__ == "__main__":
    unittest.main()
