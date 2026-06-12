"""Pygame desktop backend. The only place that deals with sprite files, sound
files and pixels."""

from pathlib import Path

import pygame

from input.events import FrameInput
from pet.intent import PetIntent, Sound
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
        self._last_rect = self._screen.get_rect()  # where the sprite was last drawn

        # Audio. Fall back to silence if there's no usable audio device.
        try:
            pygame.mixer.init()
            self._sounds = {Sound.SQUEAK: pygame.mixer.Sound(str(assets_dir / "Squeak.ogg"))}
        except pygame.error:
            self._sounds = {}

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

    def pump_events(self) -> FrameInput:
        quit_ = poked = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_ = True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self._last_rect.collidepoint(event.pos):
                    poked = True
        return FrameInput(quit=quit_, poked=poked)

    def render(self, intent: PetIntent) -> None:
        if intent.sound is not None:
            sfx = self._sounds.get(intent.sound)
            if sfx is not None:
                sfx.play()

        sprite = self._surface_for(intent)
        self._screen.fill(BACKGROUND_COLOR)
        self._last_rect = sprite.get_rect(center=self._screen.get_rect().center)
        self._screen.blit(sprite, self._last_rect)
        pygame.display.flip()
        self._clock.tick(FPS)

    def shutdown(self) -> None:
        pygame.quit()
