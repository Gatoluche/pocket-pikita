"""Choose and smoothly follow screen-space targets with Pikita's eyes.

Target sources stay outside the tracker. The renderer currently supplies the
mouse cursor only when it is on Pikita's display; future sound, notification,
or screen-change detectors can publish targets through the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class EyeTarget:
    """A point Pikita may look at, with a relative interest score."""

    position: tuple[float, float]
    interest: float = 1.0
    source: str = "cursor"


class EyeTracker:
    """Select the strongest interest and ease gaze toward it or back to center."""

    def __init__(self, pursuit_rate: float = 12.0, return_rate: float = 7.0):
        self._pursuit_rate = max(0.0, pursuit_rate)
        self._return_rate = max(0.0, return_rate)
        self._gaze = (0.0, 0.0)

    @property
    def gaze(self) -> tuple[float, float]:
        return self._gaze

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, value))

    def update(
        self,
        eye_position: tuple[float, float],
        targets: Iterable[EyeTarget],
        dt: float,
        focus_range: tuple[float, float] = (520.0, 360.0),
    ) -> tuple[float, float]:
        """Return normalized gaze after smoothing toward the most interesting point.

        ``focus_range`` is the screen-space distance from the eyes to full gaze
        deflection. The target may come from any future interest sensor.
        """
        eligible = [
            target
            for target in targets
            if target.interest > 0.0
            and math.isfinite(target.interest)
            and all(math.isfinite(value) for value in target.position)
        ]
        if eligible:
            target = max(eligible, key=lambda item: item.interest)
            range_x = max(1.0, abs(focus_range[0]))
            range_y = max(1.0, abs(focus_range[1]))
            desired = (
                self._clamp((target.position[0] - eye_position[0]) / range_x),
                self._clamp((target.position[1] - eye_position[1]) / range_y),
            )
            rate = self._pursuit_rate
        else:
            desired = (0.0, 0.0)
            rate = self._return_rate

        elapsed = max(0.0, min(0.25, dt))
        blend = 1.0 - math.exp(-rate * elapsed)
        self._gaze = (
            self._gaze[0] + (desired[0] - self._gaze[0]) * blend,
            self._gaze[1] + (desired[1] - self._gaze[1]) * blend,
        )
        return self._gaze
