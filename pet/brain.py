"""Decides what Pikita is doing each frame. For now he just sits in Base."""

from pet.intent import Expression, PetIntent


class Brain:
    def update(self) -> PetIntent:
        # TODO: real state machine (idle <-> sleep on a timer, poke reactions)
        return PetIntent(expression=Expression.BASE)
