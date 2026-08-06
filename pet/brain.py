"""Pikita's small, renderer-independent behaviour state machine."""

import random

from pet.intent import Expression, PetIntent, Sound

BLINK_DURATION = 0.12         # how long the eyes stay shut, in seconds
MIN_GAP, MAX_GAP = 2.0, 5.0   # range between blinks, in seconds
REACTION_DURATION = 0.6       # how long a poke reaction lasts, in seconds
MIN_IDLE_GAP, MAX_IDLE_GAP = 7.0, 14.0
IDLE_EXPRESSIONS = (Expression.SMUG, Expression.WINK, Expression.UNIMPRESSED)
POKE_EXPRESSIONS = (Expression.HAPPY, Expression.WINK, Expression.BLUSH)


class Brain:
    def __init__(self):
        self._eyes_shut = False
        self._timer = 0.0
        self._gap = random.uniform(MIN_GAP, MAX_GAP)
        self._reacting = 0.0  # seconds of poke reaction left
        self._reaction_expression = Expression.HAPPY
        self._idle_expression = Expression.BASE
        self._idle_timer = random.uniform(MIN_IDLE_GAP, MAX_IDLE_GAP)
        self._idle_remaining = 0.0

    def update(
        self,
        dt: float,
        poked: bool = False,
        squish_x: float = 0.0,
        squish_y: float = 0.0,
    ) -> PetIntent:
        # dt = seconds elapsed since the last frame, so timing is framerate-independent.
        if poked:
            # Start (or restart) the reaction and squeak this one frame only.
            self._reacting = REACTION_DURATION
            self._reaction_expression = random.choice(POKE_EXPRESSIONS)
            self._eyes_shut = False
            self._timer = 0.0
            return PetIntent(expression=self._reaction_expression, sound=Sound.SQUEAK)

        squishing = squish_x > 0.0 or squish_y > 0.0
        if squishing:
            return PetIntent(
                expression=Expression.HAPPY,
                squishing=True,
                squish_x=squish_x,
                squish_y=squish_y,
            )

        if self._reacting > 0.0:
            self._reacting -= dt
            return PetIntent(expression=self._reaction_expression)

        if self._idle_remaining > 0.0:
            self._idle_remaining -= dt
            return PetIntent(expression=self._idle_expression)

        self._idle_timer -= dt
        if self._idle_timer <= 0.0:
            self._idle_expression = random.choice(IDLE_EXPRESSIONS)
            self._idle_remaining = random.uniform(0.7, 1.4)
            self._idle_timer = random.uniform(MIN_IDLE_GAP, MAX_IDLE_GAP)
            return PetIntent(expression=self._idle_expression)

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
