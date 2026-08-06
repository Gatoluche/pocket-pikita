import unittest
from unittest.mock import patch

from pet.brain import BLINK_DURATION, MAX_GAP, REACTION_DURATION, SQUEAK_INTERVAL, Brain
from pet.intent import Expression, Sound


class BrainTests(unittest.TestCase):
    def test_blink_closes_and_reopens_eyes(self):
        brain = Brain()
        self.assertTrue(brain.update(MAX_GAP + 0.01).blinking)
        self.assertFalse(brain.update(BLINK_DURATION + 0.01).blinking)

    @patch("pet.brain.random.choice", return_value=Expression.WINK)
    def test_poke_squeaks_once_and_holds_expression(self, _choice):
        brain = Brain()
        first = brain.update(0.01, poked=True)
        second = brain.update(0.01)
        brain.update(REACTION_DURATION + 0.01)
        settled = brain.update(0.0)

        self.assertEqual((first.expression, first.sound), (Expression.WINK, Sound.SQUEAK))
        self.assertEqual((second.expression, second.sound), (Expression.WINK, None))
        self.assertEqual(settled.expression, Expression.BASE)

    def test_squishing_repeats_squeaks_on_a_timer(self):
        brain = Brain()
        first = brain.update(0.01, squish_x=0.5)
        quiet = brain.update(SQUEAK_INTERVAL / 2, squish_x=0.5)
        next_squeak = brain.update(SQUEAK_INTERVAL, squish_x=0.5)

        self.assertEqual(first.sound, Sound.SQUEAK)
        self.assertIsNone(quiet.sound)
        self.assertEqual(next_squeak.sound, Sound.SQUEAK)
        self.assertEqual(first.squish_x, 0.5)


if __name__ == "__main__":
    unittest.main()
