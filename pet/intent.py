"""Types describing what Pikita wants to express on a given frame.

The brain only ever produces a PetIntent and never touches sprites directly,
which keeps the door open to swapping renderers (Live2D, Pi face) later.
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


@dataclass(frozen=True)
class PetIntent:
    # talking/blinking are behaviours, not frames, so each backend can decide how
    # to show them (a Live2D rig handles blinking itself, for example).
    expression: Expression = Expression.BASE
    talking: bool = False
    blinking: bool = False
