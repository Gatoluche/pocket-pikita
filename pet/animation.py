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
# Rest is still; visible idle movement comes from sparse one-shot clips.
IDLE_CLIP = AnimationClip(
    "idle",
    1.0,
    {
        name: (Keyframe(0.0, 0.0), Keyframe(1.0, 0.0))
        for name in (
            "ear_left", "ear_right", "arm_left", "arm_right",
            "feet_left", "feet_right", "hair_left", "hair_right", "hair_front",
        )
    },
    loop=True,
)

IDLE_GLANCE_CLIP = AnimationClip(
    "idle glance",
    1.2,
    {
        "gaze_x": (
            Keyframe(0.0, 0.0), Keyframe(0.16, 0.78, "ease_out"),
            Keyframe(0.78, 0.78), Keyframe(1.2, 0.0, "ease_in"),
        ),
        "gaze_y": (
            Keyframe(0.0, 0.0), Keyframe(0.16, 0.65, "ease_out"),
            Keyframe(0.78, 0.65), Keyframe(1.2, 0.0, "ease_in"),
        ),
    },
)

IDLE_FIDGET_CLIP = AnimationClip(
    "idle foot fidget",
    0.9,
    {
        "feet_left": (
            Keyframe(0.0, 0.0), Keyframe(0.18, 2.0, "ease_out"),
            Keyframe(0.40, -0.7, "ease_out"), Keyframe(0.64, 0.25),
            Keyframe(0.9, 0.0, "ease_in"),
        ),
        "feet_right": (
            Keyframe(0.0, 0.0), Keyframe(0.18, -0.45, "ease_out"),
            Keyframe(0.40, 0.2), Keyframe(0.64, 0.0), Keyframe(0.9, 0.0),
        ),
        "foot_lift_left": (
            Keyframe(0.0, 0.0), Keyframe(0.16, 3.5, "ease_out"),
            Keyframe(0.34, 1.0, "ease_in"), Keyframe(0.52, 0.0),
            Keyframe(0.9, 0.0),
        ),
        "foot_lift_right": (
            Keyframe(0.0, 0.0), Keyframe(0.16, 0.6, "ease_out"),
            Keyframe(0.34, 0.0), Keyframe(0.9, 0.0),
        ),
        "arm_left": (
            Keyframe(0.0, 0.0), Keyframe(0.2, 0.8, "ease_out"),
            Keyframe(0.42, -0.25), Keyframe(0.9, 0.0, "ease_in"),
        ),
        "arm_right": (
            Keyframe(0.0, 0.0), Keyframe(0.2, -0.25, "ease_out"),
            Keyframe(0.42, 0.0), Keyframe(0.9, 0.0, "ease_in"),
        ),
        "hair_left": (
            Keyframe(0.0, 0.0), Keyframe(0.14, 0.75, "ease_out"),
            Keyframe(0.34, -0.3, "ease_out"), Keyframe(0.64, 0.0),
            Keyframe(0.9, 0.0),
        ),
        "hair_right": (
            Keyframe(0.0, 0.0), Keyframe(0.14, -0.25, "ease_out"),
            Keyframe(0.34, 0.15), Keyframe(0.64, 0.0), Keyframe(0.9, 0.0),
        ),
        "hair_front": (
            Keyframe(0.0, 0.0), Keyframe(0.14, -0.35, "ease_out"),
            Keyframe(0.34, 0.15), Keyframe(0.64, 0.0), Keyframe(0.9, 0.0),
        ),
    },
)

POKE_REACTION_CLIP = AnimationClip(
    "poke recoil",
    0.48,
    {
        "ear_left": (
            Keyframe(0.0, 0.0), Keyframe(0.06, -3.0, "ease_out"),
            Keyframe(0.15, 1.2, "ease_out"), Keyframe(0.30, -0.45),
            Keyframe(0.48, 0.0, "ease_in"),
        ),
        "ear_right": (
            Keyframe(0.0, 0.0), Keyframe(0.06, 3.0, "ease_out"),
            Keyframe(0.15, -1.2, "ease_out"), Keyframe(0.30, 0.45),
            Keyframe(0.48, 0.0, "ease_in"),
        ),
        "arm_left": (
            Keyframe(0.0, 0.0), Keyframe(0.08, 2.2, "ease_out"),
            Keyframe(0.19, -0.8, "ease_out"), Keyframe(0.34, 0.2),
            Keyframe(0.48, 0.0, "ease_in"),
        ),
        "arm_right": (
            Keyframe(0.0, 0.0), Keyframe(0.08, -2.2, "ease_out"),
            Keyframe(0.19, 0.8, "ease_out"), Keyframe(0.34, -0.2),
            Keyframe(0.48, 0.0, "ease_in"),
        ),
        "hair_left": (
            Keyframe(0.0, 0.0), Keyframe(0.07, 1.25, "ease_out"),
            Keyframe(0.19, -0.55, "ease_out"), Keyframe(0.34, 0.15),
            Keyframe(0.48, 0.0, "ease_in"),
        ),
        "hair_right": (
            Keyframe(0.0, 0.0), Keyframe(0.07, -1.25, "ease_out"),
            Keyframe(0.19, 0.55, "ease_out"), Keyframe(0.34, -0.15),
            Keyframe(0.48, 0.0, "ease_in"),
        ),
        "hair_front": (
            Keyframe(0.0, 0.0), Keyframe(0.07, -0.8, "ease_out"),
            Keyframe(0.19, 0.35, "ease_out"), Keyframe(0.34, -0.1),
            Keyframe(0.48, 0.0, "ease_in"),
        ),
    },
)

WALK_CLIP = AnimationClip(
    "walk",
    0.8,
    {
        "feet_left": (
            Keyframe(0.0, 0.0), Keyframe(0.2, -1.3, "ease_out"),
            Keyframe(0.4, 0.0, "ease_in"), Keyframe(0.6, 1.0, "ease_out"),
            Keyframe(0.8, 0.0, "ease_in"),
        ),
        "feet_right": (
            Keyframe(0.0, 0.0), Keyframe(0.2, 1.0, "ease_out"),
            Keyframe(0.4, 0.0, "ease_in"), Keyframe(0.6, -1.3, "ease_out"),
            Keyframe(0.8, 0.0, "ease_in"),
        ),
        # Feet are fully detached from the body; the torso and folded arms stay
        # settled while one foot swings forward and lifts, then trades places.
        "foot_stride_left": (
            Keyframe(0.0, 0.0), Keyframe(0.12, 3.0, "ease_out"),
            Keyframe(0.24, 11.0), Keyframe(0.4, 0.0, "ease_in"),
            Keyframe(0.56, -5.0), Keyframe(0.8, 0.0, "ease_in"),
        ),
        "foot_stride_right": (
            Keyframe(0.0, 0.0), Keyframe(0.2, -5.0),
            Keyframe(0.4, 0.0, "ease_in"), Keyframe(0.52, 3.0, "ease_out"),
            Keyframe(0.64, 11.0), Keyframe(0.8, 0.0, "ease_in"),
        ),
        "foot_lift_left": (
            Keyframe(0.0, 0.0), Keyframe(0.12, 2.0, "ease_out"),
            Keyframe(0.24, 9.0), Keyframe(0.4, 0.0, "ease_in"),
            Keyframe(0.8, 0.0),
        ),
        "foot_lift_right": (
            Keyframe(0.0, 0.0), Keyframe(0.4, 0.0),
            Keyframe(0.52, 2.0, "ease_out"), Keyframe(0.64, 9.0),
            Keyframe(0.8, 0.0, "ease_in"),
        ),
    },
    loop=True,
)

IMPACT_CLIP = AnimationClip(
    "impact",
    0.32,
    {
        "scale_normal": (
            Keyframe(0.0, 0.86), Keyframe(0.055, 1.05),
            Keyframe(0.16, 0.97), Keyframe(0.32, 1.0),
        ),
        "scale_tangent": (
            Keyframe(0.0, 1.08), Keyframe(0.055, 0.97),
            Keyframe(0.16, 1.02), Keyframe(0.32, 1.0),
        ),
    },
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
