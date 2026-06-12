"""Pygame desktop backend. The only place that deals with sprite files and pixels."""

from pathlib import Path

import pygame

from pet.intent import PetIntent
from render.renderer import Renderer

TARGET_HEIGHT = 600
MARGIN = 40
BACKGROUND_COLOR = (24, 26, 34)
FPS = 60


def _normalize(name: str) -> str:
    # Strip spaces + lowercase so the inconsistent filenames ("Sad + Speak.png"
    # vs "Happy +Speak.png") collapse to the same key.
    return name.removesuffix(".png").replace(" ", "").lower()


class PygameWindow(Renderer):
    def __init__(self, assets_dir: Path):
        pygame.init()
        pygame.display.set_caption("Pikita")

        # convert_alpha() needs a display to exist, but the final window size
        # depends on the scaled sprites. Open a temporary window, resize later.
        self._screen = pygame.display.set_mode((TARGET_HEIGHT, TARGET_HEIGHT))

        self._sprites: dict[str, pygame.Surface] = {}
        scale = None
        for png in sorted(assets_dir.glob("*.png")):
            image = pygame.image.load(str(png))
            if scale is None:  # lock the scale to the first sprite so they all match
                scale = TARGET_HEIGHT / image.get_height()
            size = (round(image.get_width() * scale), round(image.get_height() * scale))
            self._sprites[_normalize(png.name)] = pygame.transform.smoothscale(
                image.convert_alpha(), size
            )

        if not self._sprites:
            raise FileNotFoundError(f"No .png sprites found in {assets_dir}")

        sprite_w, sprite_h = next(iter(self._sprites.values())).get_size()
        self._screen = pygame.display.set_mode((sprite_w + MARGIN, sprite_h + MARGIN))
        self._clock = pygame.time.Clock()

    def _surface_for(self, intent: PetIntent) -> pygame.Surface:
        # Most specific sprite first, then fall back. Only Base has blink art.
        expr = intent.expression.value
        candidates = []
        if intent.blinking and intent.talking:
            candidates.append(f"{expr}+Blink+Speak")
        if intent.blinking:
            candidates.append(f"{expr}+Blink")
        if intent.talking:
            candidates.append(f"{expr}+Speak")
        candidates.append(expr)

        for key in candidates:
            sprite = self._sprites.get(_normalize(key))
            if sprite is not None:
                return sprite
        return self._sprites[_normalize("Base")]

    def pump_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
        return True

    def render(self, intent: PetIntent) -> None:
        sprite = self._surface_for(intent)
        self._screen.fill(BACKGROUND_COLOR)
        rect = sprite.get_rect(center=self._screen.get_rect().center)
        self._screen.blit(sprite, rect)
        pygame.display.flip()
        self._clock.tick(FPS)

    def shutdown(self) -> None:
        pygame.quit()
