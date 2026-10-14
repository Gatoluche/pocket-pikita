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


# These are the roots of the separated Illustrator hair shapes, in the shared
# 446x910 artboard coordinates.
TOP_HAIR_PIVOTS = {
    "left": (190.0, 238.0),
    "right": (366.0, 278.0),
    "front": (246.0, 192.0),
}


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
        self._top_hair_base = self._layers["Top Hair"]
        self._top_hair_parts: dict[str, _Part] = {}
        self._load_top_hair_parts(rig_dir)
        self._ear_led_highlights: dict[str, _Part] = {}
        self._load_ear_leds(rig_dir)

        self._face_mask = self._make_face_mask(self._layers["Faces"])
        self._extend_face_mask_over_cheeks(self._face_mask)
        self._masked_faces: dict[int, pygame.Surface] = {}
        self._gaze_base: pygame.Surface | None = None
        self._pupils: pygame.Surface | None = None
        gaze_dir = rig_dir / "eyes"
        gaze_base_path = gaze_dir / "base_without_pupils.png"
        pupils_path = gaze_dir / "pupils.png"
        if gaze_base_path.is_file() != pupils_path.is_file():
            raise FileNotFoundError(
                "Eye tracking needs both assets/rig/eyes/base_without_pupils.png "
                "and assets/rig/eyes/pupils.png"
            )
        if gaze_base_path.is_file():
            self._gaze_base = pygame.image.load(str(gaze_base_path)).convert_alpha()
            self._pupils = pygame.image.load(str(pupils_path)).convert_alpha()
            expected_size = (self._width, self._height)
            if (
                self._gaze_base.get_size() != expected_size
                or self._pupils.get_size() != expected_size
            ):
                raise ValueError(
                    f"Eye tracking images must both use the {self._width}x{self._height} "
                    "rig canvas"
                )
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

    @staticmethod
    def _make_canvas_part(
        surface: pygame.Surface, pivot: tuple[float, float]
    ) -> _Part:
        bounds = surface.get_bounding_rect(min_alpha=1)
        if bounds.width == 0 or bounds.height == 0:
            raise ValueError("An extracted hair object is empty")
        image = surface.subsurface(bounds).copy()
        return _Part(image, (bounds.x, bounds.y), pivot)

    def _load_top_hair_parts(self, rig_dir: Path) -> None:
        sublayers_dir = rig_dir / "sublayers"
        manifest_path = sublayers_dir / "manifest.json"
        composite_path = sublayers_dir / "top_hair.png"
        if not manifest_path.is_file() or not composite_path.is_file():
            return

        try:
            sublayers_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return
        entries = [
            entry
            for entry in sublayers_manifest.get("object_exports", [])
            if entry.get("layer_path") == ["Top Hair"]
            and entry.get("item_type") in ("PathItem", "CompoundPathItem")
        ]
        if len(entries) != len(TOP_HAIR_PIVOTS):
            return

        composite = pygame.image.load(str(composite_path)).convert_alpha()
        expected_size = (self._width, self._height)
        if composite.get_size() != expected_size:
            return

        surfaces: dict[str, pygame.Surface] = {}
        for entry in entries:
            filename = entry.get("file")
            if not isinstance(filename, str):
                return
            path = sublayers_dir / filename
            if not path.is_file():
                return
            try:
                surface = pygame.image.load(str(path)).convert_alpha()
            except pygame.error:
                return
            if surface.get_size() != expected_size:
                return
            bounds = surface.get_bounding_rect(min_alpha=1)
            center_x = bounds.centerx
            if center_x < 190:
                part_name = "left"
            elif center_x > 310:
                part_name = "right"
            else:
                part_name = "front"
            if part_name in surfaces or bounds.width == 0 or bounds.height == 0:
                return
            surfaces[part_name] = surface

        if set(surfaces) != set(TOP_HAIR_PIVOTS):
            return

        # Remove the extracted shapes from the static layer so their animated
        # copies never leave a doubled edge behind.
        pixels = bytearray(pygame.image.tostring(composite, "RGBA", False))
        masks = [
            pygame.image.tostring(surfaces[name], "RGBA", False)
            for name in ("left", "right", "front")
        ]
        for offset in range(3, len(pixels), 4):
            if any(mask[offset] for mask in masks):
                pixels[offset] = 0
        self._top_hair_base = pygame.image.frombuffer(
            bytes(pixels), expected_size, "RGBA"
        ).copy()
        self._top_hair_parts = {
            name: self._make_canvas_part(surface, TOP_HAIR_PIVOTS[name])
            for name, surface in surfaces.items()
        }

    def _load_ear_leds(self, rig_dir: Path) -> None:
        sublayers_dir = rig_dir / "sublayers"
        manifest_path = sublayers_dir / "manifest.json"
        if not manifest_path.is_file():
            return
        try:
            sublayers_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return

        entries = [
            entry
            for entry in sublayers_manifest.get("object_exports", [])
            if entry.get("layer_path") == ["Ear", "Ears"]
            and entry.get("item_name") == "LED"
        ]
        if len(entries) != 2:
            return

        highlights: dict[str, _Part] = {}
        for entry in entries:
            filename = entry.get("file")
            if not isinstance(filename, str):
                return
            path = sublayers_dir / filename
            if not path.is_file():
                return
            try:
                surface = pygame.image.load(str(path)).convert_alpha()
            except pygame.error:
                return
            if surface.get_size() != (self._width, self._height):
                return

            bounds = surface.get_bounding_rect(min_alpha=1)
            side = "left" if bounds.centerx < self._width / 2 else "right"
            if bounds.width == 0 or bounds.height == 0 or side in highlights:
                return

            pixels = bytearray(pygame.image.tostring(surface, "RGBA", False))
            for offset in range(0, len(pixels), 4):
                if pixels[offset + 3]:
                    # Tint the pulse amber so it stays visible against white.
                    pixels[offset : offset + 3] = b"\xff\x80\x00"
            highlight = pygame.image.frombuffer(
                bytes(pixels), surface.get_size(), "RGBA"
            ).copy()
            pivot = tuple(self._pivots["Ear"][side])
            highlights[side] = self._make_canvas_part(highlight, pivot)

        if set(highlights) == {"left", "right"}:
            self._ear_led_highlights = highlights

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

    def _gazed_face_for(
        self,
        expression_surface: pygame.Surface,
        gaze_x: float,
        gaze_y: float,
    ) -> pygame.Surface:
        if self._gaze_base is None or self._pupils is None:
            return self._face_for(expression_surface)
        offset = (
            round(max(-1.0, min(1.0, gaze_x)) * 6.0),
            round(max(-1.0, min(1.0, gaze_y)) * 3.0),
        )
        if offset == (0, 0):
            return self._face_for(expression_surface)
        face = self._gaze_base.copy()
        face.blit(self._face_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pupils = self._pupils.copy()
        pupils.blit(self._face_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        face.blit(pupils, offset)
        return face

    @staticmethod
    def _draw_rotated(
        canvas: pygame.Surface,
        part: _Part,
        angle: float,
        offset: tuple[float, float] = (0.0, 0.0),
        opacity: int = 255,
    ) -> None:
        opacity = max(0, min(255, opacity))
        if opacity == 0:
            return
        image = part.image
        if abs(angle) < 0.05:
            if opacity < 255:
                image = image.copy()
                image.set_alpha(opacity)
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
        if opacity < 255:
            rotated.set_alpha(opacity)
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
        ear_led_pulse: float = 0.0,
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
        # A slight shared tilt lets the ears follow the direction of attention.
        gaze_turn = -2.0 * max(-1.0, min(1.0, gaze_x))
        ear_left = idle_motion["ear_left"] * ear_scale + ear_flick_left + gaze_turn
        ear_right = idle_motion["ear_right"] * ear_scale + ear_flick_right + gaze_turn
        if jumping:
            ear_left -= 3.0
            ear_right += 3.0
        self._draw_rotated(canvas, self._parts["Ear"]["left"], ear_left)
        self._draw_rotated(canvas, self._parts["Ear"]["right"], ear_right)
        led_opacity = round(120 * max(0.0, min(1.0, ear_led_pulse)))
        if led_opacity:
            for side, angle in (("left", ear_left), ("right", ear_right)):
                led = self._ear_led_highlights.get(side)
                if led is not None:
                    self._draw_rotated(
                        canvas, led, angle, opacity=led_opacity
                    )

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

        canvas.blit(self._top_hair_base, (0, 0))
        for side in ("left", "right", "front"):
            part = self._top_hair_parts.get(side)
            if part is not None:
                self._draw_rotated(canvas, part, idle_motion[f"hair_{side}"])

        return canvas
