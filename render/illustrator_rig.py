"""Compose the Illustrator parts with the app's existing face expressions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pygame


@dataclass(frozen=True)
class _Part:
    image: pygame.Surface
    origin: tuple[int, int]
    pivot: tuple[float, float]


class IllustratorRig:
    """A small, software-composited rig for the separately exported layers."""

    def __init__(self, rig_dir: Path):
        self._rig_dir = rig_dir
        manifest = json.loads((rig_dir / "manifest.json").read_text(encoding="utf-8"))
        self._width, self._height = manifest["canvas_size"]
        self._pivots = manifest["paired_layer_pivots"]
        self._layers: dict[str, pygame.Surface] = {}
        for name, filename in manifest["layer_files"].items():
            path = rig_dir / "layers" / filename
            self._layers[name] = pygame.image.load(str(path)).convert_alpha()

        self._face_mask = self._make_face_mask(self._layers["Faces"])
        self._extend_face_mask_over_cheeks(self._face_mask)
        self._masked_faces: dict[int, pygame.Surface] = {}
        self._parts = {
            layer_name: {
                side: self._make_part(layer_name, side, pivot)
                for side, pivot in side_pivots.items()
            }
            for layer_name, side_pivots in self._pivots.items()
        }

    @staticmethod
    def _make_face_mask(face_shape: pygame.Surface) -> pygame.Surface:
        pixels = bytearray(pygame.image.tostring(face_shape, "RGBA", False))
        for offset in range(0, len(pixels), 4):
            pixels[offset : offset + 3] = b"\xff\xff\xff"
        return pygame.image.frombuffer(
            bytes(pixels), face_shape.get_size(), "RGBA"
        ).copy()

    @staticmethod
    def _extend_face_mask_over_cheeks(mask: pygame.Surface) -> None:
        # The PNG expressions draw the cheek patches over the edge of the
        # Illustrator faceplate. Keep those source pixels in front of it.
        pygame.draw.polygon(
            mask,
            (255, 255, 255, 255),
            ((54, 466), (139, 466), (126, 539), (72, 526)),
        )
        pygame.draw.polygon(
            mask,
            (255, 255, 255, 255),
            ((307, 466), (392, 466), (374, 526), (320, 539)),
        )

    def _make_part(
        self, layer_name: str, side: str, pivot: list[int]
    ) -> _Part:
        layer = self._layers[layer_name]
        split_x = self._width // 2
        left = 0 if side == "left" else split_x
        width = split_x if side == "left" else self._width - split_x
        half = layer.subsurface((left, 0, width, self._height))
        bounds = half.get_bounding_rect(min_alpha=1)
        if bounds.width == 0 or bounds.height == 0:
            raise ValueError(f"The {layer_name} {side} component is empty")
        image = half.subsurface(bounds).copy()
        origin = (left + bounds.x, bounds.y)
        return _Part(image, origin, (float(pivot[0]), float(pivot[1])))

    def _face_for(self, expression_surface: pygame.Surface) -> pygame.Surface:
        key = id(expression_surface)
        face = self._masked_faces.get(key)
        if face is None:
            face = expression_surface.copy()
            face.blit(
                self._face_mask,
                (0, 0),
                special_flags=pygame.BLEND_RGBA_MULT,
            )
            self._masked_faces[key] = face
        return face

    @staticmethod
    def _draw_rotated(
        canvas: pygame.Surface,
        part: _Part,
        angle: float,
        offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        image = part.image
        if abs(angle) < 0.05:
            canvas.blit(
                image,
                (
                    round(part.origin[0] + offset[0]),
                    round(part.origin[1] + offset[1]),
                ),
            )
            return

        # rotate() is unfiltered, so even tiny ear/limb movements produce
        # visibly stepped edges. rotozoom() keeps the same angle and scale
        # while filtering the transformed pixels.
        rotated = pygame.transform.rotozoom(image, angle, 1.0)
        radians = math.radians(angle)
        cosine, sine = math.cos(radians), math.sin(radians)
        center_x, center_y = image.get_width() / 2, image.get_height() / 2
        local_x = part.pivot[0] - part.origin[0]
        local_y = part.pivot[1] - part.origin[1]
        rotated_pivot_x = (
            cosine * (local_x - center_x)
            + sine * (local_y - center_y)
            + rotated.get_width() / 2
        )
        rotated_pivot_y = (
            -sine * (local_x - center_x)
            + cosine * (local_y - center_y)
            + rotated.get_height() / 2
        )
        canvas.blit(
            rotated,
            (
                round(part.pivot[0] + offset[0] - rotated_pivot_x),
                round(part.pivot[1] + offset[1] - rotated_pivot_y),
            ),
        )

    def compose(
        self,
        expression_surface: pygame.Surface,
        seconds: float,
        walking: bool = False,
        walk_strength: float = 0.0,
        jumping: bool = False,
    ) -> pygame.Surface:
        """Return one assembled frame while preserving the selected PNG face."""
        canvas = pygame.Surface(
            (self._width, self._height), pygame.SRCALPHA, 32
        )
        step = math.sin(seconds * 11.0)
        strength = max(0.0, min(1.0, walk_strength)) if walking else 0.0
        idle = 1.0 - strength

        feet_left = step * 8.0 * strength + math.sin(seconds * 0.9) * 0.45 * idle
        feet_right = step * 8.0 * strength + math.sin(seconds * 0.9 + 0.8) * 0.45 * idle
        self._draw_rotated(canvas, self._parts["Feet"]["left"], feet_left)
        self._draw_rotated(canvas, self._parts["Feet"]["right"], feet_right)

        canvas.blit(self._layers["Body"], (0, 0))
        canvas.blit(self._layers["Bottom Hair"], (0, 0))

        ear_left = math.sin(seconds * 2.2) * (2.4 + strength * 1.0)
        ear_right = math.sin(seconds * 1.9 + 1.1) * (2.4 + strength * 1.0)
        if jumping:
            ear_left -= 3.0
            ear_right += 3.0
        self._draw_rotated(canvas, self._parts["Ear"]["left"], ear_left)
        self._draw_rotated(canvas, self._parts["Ear"]["right"], ear_right)

        canvas.blit(self._layers["Faces"], (0, 0))
        canvas.blit(self._layers["Frame"], (0, 0))
        canvas.blit(self._face_for(expression_surface), (0, 0))

        arm_idle = math.sin(seconds * 1.4) * 0.9 * idle
        arm_left = step * 12.0 * strength + arm_idle
        arm_right = step * 12.0 * strength + math.sin(seconds * 1.4 + 1.2) * 0.9 * idle
        if jumping:
            arm_left += 5.0
            arm_right -= 5.0
        self._draw_rotated(canvas, self._parts["Arms"]["left"], arm_left)
        self._draw_rotated(canvas, self._parts["Arms"]["right"], arm_right)

        canvas.blit(self._layers["Top Hair"], (0, 0))

        breathing = 1.35 * math.sin(seconds * 1.8) * idle
        if abs(breathing) > 0.05:
            frame = pygame.Surface(
                (self._width, self._height), pygame.SRCALPHA, 32
            )
            frame.blit(canvas, (0, round(breathing)))
            return frame
        return canvas
