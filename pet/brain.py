"""Decides what Pikita is doing each frame.

Idle: he blinks on a random timer. Poke him and he reacts - a happy squeeze
plus a squeaky-toy noise - then settles back to idling.
"""

import random

from pet.intent import Expression, PetIntent, Sound

BLINK_DURATION = 0.12         # how long the eyes stay shut, in seconds
MIN_GAP, MAX_GAP = 2.0, 5.0   # range between blinks, in seconds
REACTION_DURATION = 0.6       # how long a poke reaction lasts, in seconds


class Brain:
    def __init__(self):
        self._eyes_shut = False
        self._timer = 0.0
        self._gap = random.uniform(MIN_GAP, MAX_GAP)
        self._reacting = 0.0  # seconds of poke reaction left

    def update(self, dt: float, poked: bool = False) -> PetIntent:
        # dt = seconds elapsed since the last frame, so timing is framerate-independent.
        if poked:
            # Start (or restart) the reaction and squeak this one frame only.
            self._reacting = REACTION_DURATION
            self._eyes_shut = False
            self._timer = 0.0
            return PetIntent(expression=Expression.HAPPY, sound=Sound.SQUEAK)

        if self._reacting > 0.0:
            self._reacting -= dt
            return PetIntent(expression=Expression.HAPPY)

        # Idle: blink on a timer.
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
