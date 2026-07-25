from __future__ import annotations

from types import SimpleNamespace
import unittest

from tkinter_utils.image_viewer import _clamp_offsets, _fit_scale, _wheel_direction
from tkinter_utils.scrollable_frame import _mousewheel_units
from tkinter_utils.theme import _validate_mode


class ScrollWheelTests(unittest.TestCase):
    def test_windows_wheel_delta(self) -> None:
        self.assertEqual(_mousewheel_units(SimpleNamespace(delta=120, num=None)), -1)
        self.assertEqual(_mousewheel_units(SimpleNamespace(delta=-240, num=None)), 2)

    def test_x11_wheel_buttons(self) -> None:
        self.assertEqual(_mousewheel_units(SimpleNamespace(delta=0, num=4)), -3)
        self.assertEqual(_mousewheel_units(SimpleNamespace(delta=0, num=5)), 3)


class ImageViewportTests(unittest.TestCase):
    def test_fit_scale_does_not_upscale_by_default(self) -> None:
        self.assertEqual(_fit_scale((100, 50), (400, 300), False), 1.0)
        self.assertEqual(_fit_scale((100, 50), (400, 300), True), 4.0)

    def test_fit_scale_uses_limiting_dimension(self) -> None:
        self.assertEqual(_fit_scale((800, 400), (400, 150), False), 0.375)

    def test_offsets_center_small_image_and_clamp_large_image(self) -> None:
        self.assertEqual(
            _clamp_offsets((-20, 50), (100, 100), (300, 200)),
            (100.0, 50.0),
        )
        self.assertEqual(
            _clamp_offsets((40, -500), (500, 400), (300, 200)),
            (0.0, -200),
        )

    def test_wheel_direction_is_cross_platform(self) -> None:
        self.assertEqual(_wheel_direction(SimpleNamespace(delta=120, num=None)), 1)
        self.assertEqual(_wheel_direction(SimpleNamespace(delta=0, num=5)), -1)


class ThemeValidationTests(unittest.TestCase):
    def test_invalid_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validate_mode("sepia")


if __name__ == "__main__":
    unittest.main()
