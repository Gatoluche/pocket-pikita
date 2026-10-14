"""Pikita's small, renderer-independent behaviour state machine."""

import random

from pet.animation import (
    EAR_FLICK_CLIP,
    IDLE_FIDGET_CLIP,
    IDLE_GLANCE_CLIP,
    POKE_REACTION_CLIP,
)
from pet.intent import Expression, PetIntent, Sound

BLINK_DURATION = 0.12         # how long the eyes stay shut, in seconds
MIN_GAP, MAX_GAP = 2.0, 5.0   # range between blinks, in seconds
DOUBLE_BLINK_CHANCE = 0.14
DOUBLE_BLINK_MIN_GAP, DOUBLE_BLINK_MAX_GAP = 0.10, 0.18
REACTION_DURATION = 0.6       # how long a poke reaction lasts, in seconds
MIN_IDLE_GAP, MAX_IDLE_GAP = 7.0, 14.0
MIN_EAR_FLICK_GAP, MAX_EAR_FLICK_GAP = 4.5, 8.0
MIN_IDLE_GLANCE_GAP, MAX_IDLE_GLANCE_GAP = 4.0, 7.0
MIN_IDLE_FIDGET_GAP, MAX_IDLE_FIDGET_GAP = 9.0, 16.0
IDLE_EXPRESSIONS = (Expression.SMUG, Expression.WINK, Expression.UNIMPRESSED)
POKE_EXPRESSIONS = (Expression.HAPPY, Expression.WINK, Expression.BLUSH)
GLANCE_DIRECTIONS = (
    (-1.0, 0.0), (1.0, 0.0), (-1.0, -1.0), (1.0, -1.0),
    (-1.0, 1.0), (1.0, 1.0),
)


class Brain:
    def __init__(self):
        self._eyes_shut = False
        self._timer = 0.0
        self._gap = random.uniform(MIN_GAP, MAX_GAP)
        self._double_blink_pending = False
        self._double_blink_followup = False
        self._reacting = 0.0  # seconds of poke reaction left
        self._reaction_elapsed = 0.0
        self._reaction_expression = Expression.HAPPY
        self._idle_expression = Expression.BASE
        self._idle_timer = random.uniform(MIN_IDLE_GAP, MAX_IDLE_GAP)
        self._idle_remaining = 0.0
        self._ear_flick_cooldown = random.uniform(MIN_EAR_FLICK_GAP, MAX_EAR_FLICK_GAP)
        self._ear_flick_elapsed: float | None = None
        self._ear_flick_side = "left"
        self._idle_glance_cooldown = random.uniform(
            MIN_IDLE_GLANCE_GAP, MAX_IDLE_GLANCE_GAP
        )
        self._idle_glance_elapsed: float | None = None
        self._idle_glance_direction = (1.0, 0.0)
        self._idle_fidget_cooldown = random.uniform(
            MIN_IDLE_FIDGET_GAP, MAX_IDLE_FIDGET_GAP
        )
        self._idle_fidget_elapsed: float | None = None
        self._idle_fidget_side = "left"

    def _interrupt_idle_motion(self) -> None:
        interrupted_blink = (
            self._eyes_shut
            or self._double_blink_pending
            or self._double_blink_followup
        )
        if interrupted_blink:
            self._eyes_shut = False
            self._timer = 0.0
            self._gap = random.uniform(MIN_GAP, MAX_GAP)
        self._double_blink_pending = False
        self._double_blink_followup = False
        self._ear_flick_elapsed = None
        self._ear_flick_cooldown = random.uniform(MIN_EAR_FLICK_GAP, MAX_EAR_FLICK_GAP)
        self._idle_glance_elapsed = None
        self._idle_glance_cooldown = random.uniform(
            MIN_IDLE_GLANCE_GAP, MAX_IDLE_GLANCE_GAP
        )
        self._idle_fidget_elapsed = None
        self._idle_fidget_cooldown = random.uniform(
            MIN_IDLE_FIDGET_GAP, MAX_IDLE_FIDGET_GAP
        )

    def _idle_motion(self, dt: float) -> dict[str, float]:
        if self._ear_flick_elapsed is None:
            self._ear_flick_cooldown -= dt
            if self._ear_flick_cooldown <= 0.0:
                self._ear_flick_elapsed = 0.0
                self._ear_flick_side = random.choice(("left", "right"))
        if self._ear_flick_elapsed is not None:
            self._ear_flick_elapsed += dt
            if self._ear_flick_elapsed >= EAR_FLICK_CLIP.duration:
                self._ear_flick_elapsed = None
                self._ear_flick_cooldown = random.uniform(
                    MIN_EAR_FLICK_GAP, MAX_EAR_FLICK_GAP
                )
                flick = 0.0
            else:
                flick = EAR_FLICK_CLIP.sample(self._ear_flick_elapsed)["rotation"]
        else:
            flick = 0.0

        return {
            "ear_flick_left": flick if self._ear_flick_side == "left" else 0.0,
            "ear_flick_right": flick if self._ear_flick_side == "right" else 0.0,
        }

    def _idle_glance(self, dt: float) -> dict[str, float]:
        if self._idle_glance_elapsed is None:
            self._idle_glance_cooldown -= dt
            if self._idle_glance_cooldown <= 0.0:
                self._idle_glance_elapsed = 0.0
                self._idle_glance_direction = random.choice(GLANCE_DIRECTIONS)

        if self._idle_glance_elapsed is None:
            return {"gaze_x": 0.0, "gaze_y": 0.0}

        self._idle_glance_elapsed += dt
        if self._idle_glance_elapsed >= IDLE_GLANCE_CLIP.duration:
            self._idle_glance_elapsed = None
            self._idle_glance_cooldown = random.uniform(
                MIN_IDLE_GLANCE_GAP, MAX_IDLE_GLANCE_GAP
            )
            return {"gaze_x": 0.0, "gaze_y": 0.0}

        glance = IDLE_GLANCE_CLIP.sample(self._idle_glance_elapsed)
        direction_x, direction_y = self._idle_glance_direction
        return {
            "gaze_x": glance["gaze_x"] * direction_x,
            "gaze_y": glance["gaze_y"] * direction_y,
            "ear_led_pulse": glance["ear_led_pulse"],
        }

    def _idle_fidget(self, dt: float) -> tuple[float | None, str]:
        if self._idle_fidget_elapsed is None:
            self._idle_fidget_cooldown -= dt
            if self._idle_fidget_cooldown <= 0.0:
                self._idle_fidget_elapsed = 0.0
                self._idle_fidget_side = (
                    "right" if self._idle_fidget_side == "left" else "left"
                )

        if self._idle_fidget_elapsed is None:
            return None, self._idle_fidget_side

        self._idle_fidget_elapsed += dt
        if self._idle_fidget_elapsed >= IDLE_FIDGET_CLIP.duration:
            self._idle_fidget_elapsed = None
            self._idle_fidget_cooldown = random.uniform(
                MIN_IDLE_FIDGET_GAP, MAX_IDLE_FIDGET_GAP
            )
            return None, self._idle_fidget_side

        progress = self._idle_fidget_elapsed / IDLE_FIDGET_CLIP.duration
        return progress, self._idle_fidget_side

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
            self._reaction_elapsed = 0.0
            self._reaction_expression = random.choice(POKE_EXPRESSIONS)
            self._eyes_shut = False
            self._timer = 0.0
            self._interrupt_idle_motion()
            return PetIntent(
                expression=self._reaction_expression,
                sound=Sound.SQUEAK,
                startle_progress=0.0,
            )

        squishing = squish_x > 0.0 or squish_y > 0.0
        if squishing:
            self._interrupt_idle_motion()
            return PetIntent(
                expression=Expression.HAPPY,
                squishing=True,
                squish_x=squish_x,
                squish_y=squish_y,
            )

        if self._reacting > 0.0:
            self._reacting -= dt
            self._reaction_elapsed += dt
            return PetIntent(
                expression=self._reaction_expression,
                startle_progress=(
                    min(1.0, self._reaction_elapsed / POKE_REACTION_CLIP.duration)
                    if self._reaction_elapsed < POKE_REACTION_CLIP.duration
                    else None
                ),
            )

        if self._idle_remaining > 0.0:
            self._idle_remaining -= dt
            return PetIntent(expression=self._idle_expression)

        self._idle_timer -= dt
        if self._idle_timer <= 0.0:
            self._interrupt_idle_motion()
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
                if self._double_blink_pending:
                    self._double_blink_pending = False
                    self._double_blink_followup = True
                    self._gap = random.uniform(
                        DOUBLE_BLINK_MIN_GAP, DOUBLE_BLINK_MAX_GAP
                    )
                else:
                    self._gap = random.uniform(MIN_GAP, MAX_GAP)
        elif self._timer >= self._gap:
            self._eyes_shut = True
            self._timer = 0.0
            if self._double_blink_followup:
                self._double_blink_followup = False
            else:
                self._double_blink_pending = (
                    random.random() < DOUBLE_BLINK_CHANCE
                )

        idle_motion = self._idle_motion(dt)
        idle_motion.update(self._idle_glance(dt))
        fidget_progress, fidget_side = self._idle_fidget(dt)
        return PetIntent(
            expression=Expression.BASE,
            blinking=self._eyes_shut,
            idle_fidget_progress=fidget_progress,
            idle_fidget_side=fidget_side,
            **idle_motion,
        )
