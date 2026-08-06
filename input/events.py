"""Input collected during one frame."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameInput:
    quit: bool = False
    poked: bool = False
    squish_x: float = 0.0
    squish_y: float = 0.0
