"""Base class every rendering backend implements."""

from abc import ABC, abstractmethod

from pet.intent import PetIntent


class Renderer(ABC):
    @abstractmethod
    def pump_events(self) -> bool:
        # Handle window/OS events. Return False when it's time to quit.
        ...

    @abstractmethod
    def render(self, intent: PetIntent) -> None:
        ...

    @abstractmethod
    def shutdown(self) -> None:
        ...
