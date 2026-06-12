"""Decides what Pikita is doing each frame.

Right now that's just blinking: eyes open for a random gap, then a quick blink.
The random gap keeps it from looking metronomic.
"""

import random

from pet.intent import Expression, PetIntent

BLINK_DURATION = 0.12      # how long the eyes stay shut, in seconds
MIN_GAP, MAX_GAP = 2.0, 5.0  # range between blinks, in seconds


class Brain:
    def __init__(self):
        self._eyes_shut = False
        self._timer = 0.0
        self._gap = random.uniform(MIN_GAP, MAX_GAP)

    def update(self, dt: float) -> PetIntent:
        # dt = seconds elapsed since the last frame, so timing is framerate-independent.
        self._timer += dt
        if self._eyes_shut:
            if self._timer >= BLINK_DURATION:
                self._eyes_shut = False
                self._timer = 0.0
                self._gap = random.uniform(MIN_GAP, MAX_GAP)
        elif self._timer >= self._gap:
            self._eyes_shut = True
            self._timer = 0.0

        return PetIntent(expression=Expression.BASE, blinking=self._eyes_shut)
