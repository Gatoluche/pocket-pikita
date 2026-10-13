"""Compose the Illustrator parts with the app's existing face expressions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pygame

from pet.animation import IDLE_CLIP, WALK_CLIP


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
        self._gaze_source: pygame.Surface | None = None
        self._gaze_background: pygame.Surface | None = None
        self._gaze_patch: pygame.Surface | None = None
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
    def _pupil_regions() -> tuple[tuple[list[tuple[int, int]], tuple[int, int, int, int]], ...]:
        # These small interior masks come from the current Base PNG, not the
        # differently styled "Eyes V4" Illustrator layer. Keep the art's pupil
        # contours fixed while shifting its shaded centers and catchlights.
        return (
            (
                [(130, 397), (143, 395), (158, 397), (168, 402), (174, 409),
                 (171, 418), (166, 425), (157, 430), (146, 430), (137, 426),
                 (131, 419), (128, 410), (128, 403)],
                (137, 387, 12, 10),
            ),
            (
                [(271, 397), (284, 395), (299, 397), (309, 402), (315, 409),
                 (312, 418), (307, 425), (298, 430), (287, 430), (278, 426),
                 (272, 419), (269, 410), (269, 403)],
                (278, 387, 12, 10),
            ),
        )

    def _prepare_gaze(self, expression_surface: pygame.Surface) -> None:
        background = expression_surface.copy()
        patch = pygame.Surface(expression_surface.get_size(), pygame.SRCALPHA, 32)
        for polygon, (center_x, center_y, radius_x, radius_y) in self._pupil_regions():
            pupil_mask = pygame.Surface(expression_surface.get_size())
            pupil_mask.fill((0, 0, 0))
            pygame.draw.polygon(pupil_mask, (255, 255, 255), polygon)
            x0 = max(0, min(point[0] for point in polygon) - 2)
            x1 = min(expression_surface.get_width(), max(point[0] for point in polygon) + 3)
            y0 = max(0, min(point[1] for point in polygon) - 2)
            y1 = min(expression_surface.get_height(), max(point[1] for point in polygon) + 3)
            for x in range(x0, x1):
                for y in range(y0, y1):
                    if pupil_mask.get_at((x, y)).r == 0:
                        continue
                    color = expression_surface.get_at((x, y))
                    if color.r == color.g == color.b and 12 <= color.r <= 60:
                        patch.set_at((x, y), color)
                        background.set_at((x, y), (0, 0, 0, color.a))

            for x in range(center_x - radius_x, center_x + radius_x + 1):
                for y in range(center_y - radius_y, center_y + radius_y + 1):
                    within_highlight = (
                        ((x - center_x) / radius_x) ** 2
                        + ((y - center_y) / radius_y) ** 2
                        <= 1.0
                    )
                    if not within_highlight:
                        continue
                    color = expression_surface.get_at((x, y))
                    if color.r == color.g == color.b and color.r >= 200:
                        patch.set_at((x, y), color)
                        background.set_at((x, y), (0, 0, 0, color.a))

        self._gaze_source = expression_surface
        self._gaze_background = background
        self._gaze_patch = patch

    def _gazed_face_for(
        self,
        expression_surface: pygame.Surface,
        gaze_x: float,
        gaze_y: float,
    ) -> pygame.Surface:
        if expression_surface is not self._gaze_source:
            self._prepare_gaze(expression_surface)
        offset = (
            round(max(-1.0, min(1.0, gaze_x)) * 6.0),
            round(max(-1.0, min(1.0, gaze_y)) * 3.0),
        )
        if offset == (0, 0):
            return self._face_for(expression_surface)
        assert self._gaze_background is not None and self._gaze_patch is not None
        face = self._gaze_background.copy()
        face.blit(self._gaze_patch, offset)
        face.blit(self._face_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
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
        gaze_x: float = 0.0,
        gaze_y: float = 0.0,
        ear_flick_left: float = 0.0,
        ear_flick_right: float = 0.0,
    ) -> pygame.Surface:
        """Return one assembled frame while preserving the selected PNG face."""
        canvas = pygame.Surface(
            (self._width, self._height), pygame.SRCALPHA, 32
        )
        strength = max(0.0, min(1.0, walk_strength)) if walking else 0.0
        idle = 1.0 - strength
        idle_motion = IDLE_CLIP.sample(seconds)
        walk_motion = WALK_CLIP.sample(seconds)

        feet_left = walk_motion.get("feet_left", 0.0) * strength + idle_motion["feet_left"] * idle
        feet_right = walk_motion.get("feet_right", 0.0) * strength + idle_motion["feet_right"] * idle
        self._draw_rotated(canvas, self._parts["Feet"]["left"], feet_left)
        self._draw_rotated(canvas, self._parts["Feet"]["right"], feet_right)

        canvas.blit(self._layers["Body"], (0, 0))
        canvas.blit(self._layers["Bottom Hair"], (0, 0))

        ear_scale = 1.0 + 0.4 * strength
        ear_left = idle_motion["ear_left"] * ear_scale + ear_flick_left
        ear_right = idle_motion["ear_right"] * ear_scale + ear_flick_right
        if jumping:
            ear_left -= 3.0
            ear_right += 3.0
        self._draw_rotated(canvas, self._parts["Ear"]["left"], ear_left)
        self._draw_rotated(canvas, self._parts["Ear"]["right"], ear_right)

        canvas.blit(self._layers["Faces"], (0, 0))
        canvas.blit(self._layers["Frame"], (0, 0))
        face = (
            self._gazed_face_for(expression_surface, gaze_x, gaze_y)
            if gaze_x or gaze_y
            else self._face_for(expression_surface)
        )
        canvas.blit(face, (0, 0))

        arm_left = walk_motion.get("arm_left", 0.0) * strength + idle_motion["arm_left"] * idle
        arm_right = walk_motion.get("arm_right", 0.0) * strength + idle_motion["arm_right"] * idle
        if jumping:
            arm_left += 5.0
            arm_right -= 5.0
        self._draw_rotated(canvas, self._parts["Arms"]["left"], arm_left)
        self._draw_rotated(canvas, self._parts["Arms"]["right"], arm_right)

        canvas.blit(self._layers["Top Hair"], (0, 0))

        breathing = idle_motion["breathing"] * idle
        if abs(breathing) > 0.05:
            frame = pygame.Surface(
                (self._width, self._height), pygame.SRCALPHA, 32
            )
            frame.blit(canvas, (0, round(breathing)))
            return frame
        return canvas
