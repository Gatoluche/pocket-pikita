"""Entry point. Run with: python main.py"""

from pathlib import Path

from pet.brain import Brain
from render.pygame_window import PygameWindow

# Resolve assets relative to this file so it runs from any working directory.
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def main() -> None:
    brain = Brain()
    renderer = PygameWindow(ASSETS_DIR)  # swap this line for a different backend

    try:
        running = True
        while running:
            running = renderer.pump_events()  # sense
            intent = brain.update()           # think
            renderer.render(intent)           # draw
    finally:
        renderer.shutdown()


if __name__ == "__main__":
    main()
