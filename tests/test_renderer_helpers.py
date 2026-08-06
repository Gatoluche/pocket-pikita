import math
import unittest

import pygame

from render.opengl_window import (
    _clean_transparent_edge,
    _grab_angle,
    _jump_motion,
    _normalize,
    _perspective_scale,
    _rotated_quad,
    _rotation_fit,
    _squish_from_drag,
    _walk_offset,
    _walk_speed_scale,
)


class RendererHelperTests(unittest.TestCase):
    def test_hair_grab_swings_opposite_horizontal_drag(self):
        self.assertGreater(_grab_angle((150, 40), (300, 600), 500.0), 0.0)
        self.assertLess(_grab_angle((150, 40), (300, 600), -500.0), 0.0)

    def test_leg_grab_flips_the_sprite(self):
        self.assertGreater(abs(_grab_angle((40, 590), (300, 600), 0.0)), 170.0)

    def test_rotated_quad_keeps_its_center(self):
        corners = _rotated_quad(10, 20, 100, 200, 37.0)
        center_x = sum(point[0] for point in corners) / 4
        center_y = sum(point[1] for point in corners) / 4
        self.assertAlmostEqual(center_x, 60.0)
        self.assertAlmostEqual(center_y, 120.0)

    def test_sideways_sprite_is_scaled_to_fit_its_canvas(self):
        self.assertAlmostEqual(_rotation_fit(300, 600, 90, (300, 600)), 0.5)
        self.assertAlmostEqual(_rotation_fit(300, 600, 180, (300, 600)), 1.0)

    def test_translucent_sprite_edges_do_not_keep_white_rgb(self):
        surface = pygame.Surface((2, 1), pygame.SRCALPHA)
        surface.set_at((0, 0), (255, 255, 255, 128))
        surface.set_at((1, 0), (255, 255, 255, 255))

        cleaned = _clean_transparent_edge(surface)

        self.assertEqual(cleaned.get_at((0, 0)), (0, 0, 0, 128))
        self.assertEqual(cleaned.get_at((1, 0)), (255, 255, 255, 255))

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

    def test_walk_speed_pulses_with_the_gait(self):
        self.assertLess(_walk_speed_scale(0.0), _walk_speed_scale(math.pi / 22))

    def test_perspective_makes_the_top_of_a_screen_feel_farther_away(self):
        self.assertLess(_perspective_scale(600, 0, 1440), _perspective_scale(1400, 0, 1440))

    def test_perspective_keeps_the_original_size_at_screen_middle(self):
        self.assertEqual(_perspective_scale(720, 0, 1440), 1.0)

    def test_perspective_halves_pikita_when_his_hair_touches_screen_top(self):
        self.assertEqual(_perspective_scale(0, 0, 1440), 0.5)

    def test_jump_motion_leaves_the_ground_mid_jump(self):
        _, bob, width, height = _jump_motion(0.5)
        self.assertLess(bob, 0.0)
        self.assertLess(width, 1.0)
        self.assertGreater(height, 1.0)


if __name__ == "__main__":
    unittest.main()
