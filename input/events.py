"""What the user did this frame, kept separate from how we read it.

Today the pygame window fills this in from mouse/window events. Later the Pi
build can fill the same struct from a touch sensor or wake-word, and nothing
downstream has to change.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameInput:
    quit: bool = False   # user closed the window
    poked: bool = False  # user clicked on Pikita this frame
