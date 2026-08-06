import math
import unittest

from render.opengl_window import _normalize, _squish_from_drag, _walk_offset


class RendererHelperTests(unittest.TestCase):
    def test_asset_names_are_normalized(self):
        self.assertEqual(_normalize("Sad + Speak.png"), "sad+speak")

    def test_horizontal_inward_drag_squishes_horizontally(self):
        x, y = _squish_from_drag((10, 300), (80, 300), (300, 600))
        self.assertGreater(x, 0.0)
        self.assertEqual(y, 0.0)

    def test_vertical_outward_drag_does_not_squish(self):
        x, y = _squish_from_drag((150, 50), (150, 10), (300, 600))
        self.assertEqual((x, y), (0.0, 0.0))

    def test_diagonal_inward_drag_squishes_both_axes(self):
        x, y = _squish_from_drag((20, 80), (80, 180), (300, 600))
        self.assertGreater(x, 0.0)
        self.assertGreater(y, 0.0)

    def test_walk_gait_is_still_while_resting(self):
        self.assertEqual(_walk_offset(False, 1.2), (0.0, 0.0))

    def test_walk_gait_sways_and_bobs_when_moving(self):
        sway, bob = _walk_offset(True, math.pi / 22)
        self.assertGreater(sway, 0.0)
        self.assertLess(bob, 0.0)


if __name__ == "__main__":
    unittest.main()
