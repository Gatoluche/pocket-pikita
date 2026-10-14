"""Small keyframed animation clips shared by the pet's brain and renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Keyframe:
    """A scalar value at a clip time, with easing into this keyframe."""

    time: float
    value: float
    easing: str = "smooth"


@dataclass(frozen=True)
class AnimationClip:
    """Named tracks of scalar keyframes, sampled at any elapsed time."""

    name: str
    duration: float
    tracks: Mapping[str, tuple[Keyframe, ...]]
    loop: bool = False

    def sample(self, seconds: float) -> dict[str, float]:
        """Sample every track; looping clips wrap, one-shots hold their end."""
        if self.duration <= 0.0:
            raise ValueError("Animation clip duration must be positive")

        time = seconds % self.duration if self.loop else max(0.0, min(seconds, self.duration))
        return {name: self._sample_track(keys, time) for name, keys in self.tracks.items()}

    @staticmethod
    def _sample_track(keys: tuple[Keyframe, ...], time: float) -> float:
        if not keys:
            return 0.0
        if time <= keys[0].time:
            return keys[0].value
        for start, end in zip(keys, keys[1:]):
            if time <= end.time:
                span = end.time - start.time
                if span <= 0.0:
                    return end.value
                progress = max(0.0, min(1.0, (time - start.time) / span))
                if end.easing == "smooth":
                    progress = progress * progress * (3.0 - 2.0 * progress)
                elif end.easing == "ease_in":
                    progress *= progress
                elif end.easing == "ease_out":
                    progress = 1.0 - (1.0 - progress) ** 2
                elif end.easing != "linear":
                    raise ValueError(f"Unknown keyframe easing: {end.easing}")
                return start.value + (end.value - start.value) * progress
        return keys[-1].value


# These clips are intentionally ordinary data: adding an authored movement does
# not require changing the compositor's interpolation code.
IDLE_CLIP = AnimationClip(
    "idle",
    8.0,
    {
        "ear_left": (
            Keyframe(0.0, 0.0), Keyframe(2.0, 2.4), Keyframe(4.0, 0.0),
            Keyframe(6.0, -2.4), Keyframe(8.0, 0.0),
        ),
        "ear_right": (
            Keyframe(0.0, 1.6), Keyframe(2.0, -1.6), Keyframe(4.0, 1.6),
            Keyframe(6.0, -1.6), Keyframe(8.0, 1.6),
        ),
        "arm_left": (
            Keyframe(0.0, 0.0), Keyframe(2.0, 0.9), Keyframe(4.0, 0.0),
            Keyframe(6.0, -0.9), Keyframe(8.0, 0.0),
        ),
        "arm_right": (
            Keyframe(0.0, 0.84), Keyframe(2.0, -0.84), Keyframe(4.0, 0.84),
            Keyframe(6.0, -0.84), Keyframe(8.0, 0.84),
        ),
        "feet_left": (
            Keyframe(0.0, 0.0), Keyframe(2.0, 0.45), Keyframe(4.0, 0.0),
            Keyframe(6.0, -0.45), Keyframe(8.0, 0.0),
        ),
        "feet_right": (
            Keyframe(0.0, 0.32), Keyframe(2.0, -0.32), Keyframe(4.0, 0.32),
            Keyframe(6.0, -0.32), Keyframe(8.0, 0.32),
        ),
        "hair_left": (
            Keyframe(0.0, 0.0), Keyframe(2.0, 1.1), Keyframe(4.0, 0.0),
            Keyframe(6.0, -1.1), Keyframe(8.0, 0.0),
        ),
        "hair_right": (
            Keyframe(0.0, 0.0), Keyframe(2.0, -1.3), Keyframe(4.0, 0.0),
            Keyframe(6.0, 1.3), Keyframe(8.0, 0.0),
        ),
        "hair_front": (
            Keyframe(0.0, 0.0), Keyframe(2.0, 0.7), Keyframe(4.0, 0.0),
            Keyframe(6.0, -0.7), Keyframe(8.0, 0.0),
        ),
    },
    loop=True,
)

IDLE_GLANCE_CLIP = AnimationClip(
    "idle glance",
    1.2,
    {
        "gaze_x": (
            Keyframe(0.0, 0.0), Keyframe(0.16, 0.42, "ease_out"),
            Keyframe(0.78, 0.42), Keyframe(1.2, 0.0, "ease_in"),
        ),
        "gaze_y": (
            Keyframe(0.0, 0.0), Keyframe(0.16, 0.16, "ease_out"),
            Keyframe(0.78, 0.16), Keyframe(1.2, 0.0, "ease_in"),
        ),
        "ear_led_pulse": (
            Keyframe(0.0, 0.0), Keyframe(0.16, 1.0, "ease_out"),
            Keyframe(0.78, 1.0), Keyframe(1.2, 0.0, "ease_in"),
        ),
    },
)

WALK_CLIP = AnimationClip(
    "walk",
    1.2,
    {
        "feet_left": (
            Keyframe(0.0, 0.0), Keyframe(0.3, 8.0), Keyframe(0.6, 0.0),
            Keyframe(0.9, -8.0), Keyframe(1.2, 0.0),
        ),
        "feet_right": (
            Keyframe(0.0, -8.0), Keyframe(0.3, 0.0), Keyframe(0.6, 8.0),
            Keyframe(0.9, 0.0), Keyframe(1.2, -8.0),
        ),
        "arm_left": (
            Keyframe(0.0, 0.0), Keyframe(0.3, -12.0), Keyframe(0.6, 0.0),
            Keyframe(0.9, 12.0), Keyframe(1.2, 0.0),
        ),
        "arm_right": (
            Keyframe(0.0, 0.0), Keyframe(0.3, 12.0), Keyframe(0.6, 0.0),
            Keyframe(0.9, -12.0), Keyframe(1.2, 0.0),
        ),
    },
    loop=True,
)

EAR_FLICK_CLIP = AnimationClip(
    "ear flick",
    0.72,
    {
        "rotation": (
            Keyframe(0.0, 0.0), Keyframe(0.12, 0.0),
            Keyframe(0.23, -8.0, "ease_out"), Keyframe(0.35, 3.5, "ease_in"),
            Keyframe(0.48, -2.0, "ease_out"), Keyframe(0.72, 0.0, "ease_in"),
        ),
    },
)
