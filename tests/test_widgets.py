from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import unittest

from tkinter_utils import ImageViewer, ScrollableFrame, load_theme, set_theme


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


class ScrollableFrameTests(TkTestCase):
    def test_exposes_content_and_matches_canvas_width(self) -> None:
        frame = ScrollableFrame(self.root, padding=8)
        frame.pack(fill="both", expand=True)
        for row in range(40):
            ttk.Label(frame.content, text=f"Row {row}").grid(row=row, sticky="w")
        self.root.update()

        self.assertIs(frame.inner, frame.content)
        self.assertGreater(frame.canvas.bbox("all")[3], frame.canvas.winfo_height())
        self.assertEqual(
            round(float(frame.canvas.itemcget(frame._window_id, "width"))),
            frame.canvas.winfo_width(),
        )


class ImageViewerTests(TkTestCase):
    def test_set_image_fits_and_coordinate_round_trips(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")

        viewer = ImageViewer(self.root)
        viewer.pack(fill="both", expand=True)
        self.root.update()
        viewer.set_image(Image.new("RGB", (800, 400), "navy"))
        self.root.update()

        self.assertIsNotNone(viewer.image)
        canvas_point = viewer.image_to_canvas(300, 200)
        image_point = viewer.canvas_to_image(*canvas_point)
        self.assertAlmostEqual(image_point[0], 300)
        self.assertAlmostEqual(image_point[1], 200)


class ThemeTests(TkTestCase):
    def test_azure_theme_loads_and_switches(self) -> None:
        self.assertTrue(load_theme(self.root, "light", fallback=None))
        self.assertEqual(ttk.Style(self.root).theme_use(), "azure-light")
        set_theme(self.root, "dark")
        self.assertEqual(ttk.Style(self.root).theme_use(), "azure-dark")


if __name__ == "__main__":
    unittest.main()
