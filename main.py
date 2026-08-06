"""Entry point. Run with: python main.py"""

import time
from pathlib import Path

from pet.brain import Brain
from render.opengl_window import OpenGLWindow

# Resolve assets relative to this file so it runs from any working directory.
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def main() -> None:
    brain = Brain()
    renderer = OpenGLWindow(ASSETS_DIR)

    try:
        running = True
        last = time.monotonic()
        while running:
            now = time.monotonic()
            dt = now - last          # seconds since the previous frame
            last = now

            user = renderer.pump_events()         # sense
            if user.quit:
                running = False
            intent = brain.update(
                dt,
                poked=user.poked,
                squish_x=user.squish_x,
                squish_y=user.squish_y,
            )
            renderer.render(intent)                      # draw
    finally:
        renderer.shutdown()


if __name__ == "__main__":
    main()
