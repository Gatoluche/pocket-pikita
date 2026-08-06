import unittest
from unittest.mock import patch

from pet.brain import BLINK_DURATION, MAX_GAP, REACTION_DURATION, Brain
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

    def test_squishing_is_a_held_state_not_squeak_spam(self):
        brain = Brain()
        first = brain.update(0.01, squish_x=0.5)
        held = brain.update(1.0, squish_x=0.5)

        self.assertIsNone(first.sound)
        self.assertTrue(first.squishing)
        self.assertTrue(held.squishing)
        self.assertEqual(first.squish_x, 0.5)


if __name__ == "__main__":
    unittest.main()
