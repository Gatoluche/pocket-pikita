"""Types describing what Pikita wants to express on a given frame.

The brain only ever produces a PetIntent and never touches sprites or sound
files directly, which keeps the door open to swapping renderers (Live2D, Pi
face/speaker) later.
"""

from dataclasses import dataclass
from enum import Enum


class Expression(Enum):
    BASE = "Base"
    HAPPY = "Happy"
    SAD = "Sad"
    ANGRY = "Angry"
    BLUSH = "Blush"
    SMUG = "Smug"
    UNIMPRESSED = "Unimpressed"
    WINK = "Wink"


class Sound(Enum):
    # Semantic cues, not filenames. The renderer decides which audio file to play.
    SQUEAK = "squeak"


@dataclass(frozen=True)
class PetIntent:
    # talking/blinking are behaviours, not frames, so each backend can decide how
    # to show them. `sound` is a one-shot cue: set only on the frame it should
    # fire, None otherwise (so it isn't replayed every frame).
    expression: Expression = Expression.BASE
    talking: bool = False
    blinking: bool = False
    sound: Sound | None = None
