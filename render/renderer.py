"""Base class every rendering backend implements."""

from abc import ABC, abstractmethod

from input.events import FrameInput
from pet.intent import PetIntent


class Renderer(ABC):
    @abstractmethod
    def pump_events(self) -> FrameInput:
        # Read window/OS events and report what the user did this frame.
        ...

    @abstractmethod
    def render(self, intent: PetIntent) -> None:
        ...

    @abstractmethod
    def shutdown(self) -> None:
        ...
