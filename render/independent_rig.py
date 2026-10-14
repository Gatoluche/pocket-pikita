"""Render independently exported Illustrator parts with damped motion lag."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import pygame

from pet.animation import (
    IDLE_CLIP,
    IDLE_FIDGET_CLIP,
    POKE_REACTION_CLIP,
    WALK_CLIP,
)


@dataclass(frozen=True)
class _Part:
    image: pygame.Surface
    origin: tuple[int, int]
    pivot: tuple[float, float]
    role: str
    side: str | None
    max_angle: float
    z: int


@dataclass
class _Spring:
    angle: float = 0.0
    speed: float = 0.0

    def step(self, target: float, dt: float) -> float:
        stiffness, damping = 62.0, 15.5
        acceleration = (target - self.angle) * stiffness - self.speed * damping
        self.speed += acceleration * dt
        self.angle += self.speed * dt
        return self.angle


class IndependentPartRig:
    """Assemble each moving body part from an aligned transparent PNG."""

    def __init__(self, rig_dir: Path):
        self.rig_dir = rig_dir
        parts_dir = rig_dir / "parts"
        self.manifest = json.loads(
            (parts_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.width, self.height = self.manifest["canvas_size"]
        self.parts: dict[str, _Part] = {}
        self._part_order = list(self.manifest["draw_order"])
        for name, entry in self.manifest["parts"].items():
            image = pygame.image.load(str(parts_dir / entry["file"])).convert_alpha()
            if image.get_size() != (self.width, self.height):
                raise ValueError(
                    f"Rig part {name} is {image.get_size()}, expected "
                    f"{self.width}x{self.height}"
                )
            bounds = image.get_bounding_rect(min_alpha=1)
            if bounds.width and bounds.height:
                cropped = image.subsurface(bounds).copy()
                origin = (bounds.x, bounds.y)
            else:
                cropped = image
                origin = (0, 0)
            self.parts[name] = _Part(
                cropped,
                origin,
                (float(entry["pivot"][0]), float(entry["pivot"][1])),
                entry["role"],
                entry.get("side"),
                float(entry.get("max_angle", 0.0)),
                int(entry.get("z", 0)),
            )
        missing = set(self._part_order) - set(self.parts)
        if missing:
            raise ValueError(f"Rig draw order references missing parts: {sorted(missing)}")

        faces = pygame.image.load(str(rig_dir / "layers" / "faces.png")).convert_alpha()
        self._face_mask = self._make_face_mask(faces)
        self._extend_face_mask_over_cheeks(self._face_mask)
        self._masked_faces: dict[int, pygame.Surface] = {}
        self._springs: dict[str, _Spring] = {}
        self._frame_angles: dict[str, float] = {}
        self._last_compose_time: float | None = None
        self._eye_assets = self._load_verified_eye_assets(rig_dir / "eyes")
        self.has_clipped_eye_tracking = self._eye_assets is not None

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

    @staticmethod
    def _load_verified_eye_assets(eyes_dir: Path) -> dict | None:
        manifest_path = eyes_dir / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if manifest.get("unmasked_pupils") is not True:
            return None
        required = [
            eyes_dir / "pupil_fill.png",
            eyes_dir / "pupils_left.png",
            eyes_dir / "pupils_right.png",
            eyes_dir / "pupil_clip_left.png",
            eyes_dir / "pupil_clip_right.png",
        ]
        if not all(path.is_file() for path in required):
            return None
        surfaces = {
            path.stem: pygame.image.load(str(path)).convert_alpha()
            for path in required
        }
        size = tuple(manifest.get("canvas_size", ()))
        if size != (446, 910) or any(surface.get_size() != size for surface in surfaces.values()):
            return None
        return surfaces

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

    def _face_with_gaze(
        self,
        expression_surface: pygame.Surface,
        gaze_x: float,
        gaze_y: float,
    ) -> pygame.Surface:
        face = self._face_for(expression_surface).copy()
        if self._eye_assets is None:
            return face
        face.blit(self._eye_assets["pupil_fill"], (0, 0))
        offset = (
            round(max(-1.0, min(1.0, gaze_x)) * 6.0),
            round(max(-1.0, min(1.0, gaze_y)) * 3.0),
        )
        for side in ("left", "right"):
            pupil = pygame.Surface((self.width, self.height), pygame.SRCALPHA, 32)
            pupil.blit(self._eye_assets[f"pupils_{side}"], offset)
            pupil.blit(
                self._eye_assets[f"pupil_clip_{side}"],
                (0, 0),
                special_flags=pygame.BLEND_RGBA_MULT,
            )
            pupil.blit(
                self._face_mask,
                (0, 0),
                special_flags=pygame.BLEND_RGBA_MULT,
            )
            face.blit(pupil, (0, 0))
        return face

    @staticmethod
    def _rotation(image: pygame.Surface, pivot: tuple[float, float], origin: tuple[int, int], angle: float):
        if abs(angle) < 0.05:
            return image, origin
        rotated = pygame.transform.rotozoom(image, angle, 1.0)
        radians = math.radians(angle)
        cosine, sine = math.cos(radians), math.sin(radians)
        center_x, center_y = image.get_width() / 2, image.get_height() / 2
        local_x, local_y = pivot[0] - origin[0], pivot[1] - origin[1]
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
        return rotated, (
            round(pivot[0] - rotated_pivot_x),
            round(pivot[1] - rotated_pivot_y),
        )

    def _spring_angle(
        self,
        key: str,
        part: _Part,
        velocity_x: float,
        dt: float,
    ) -> float:
        if part.max_angle <= 0.0:
            return 0.0
        if key in self._frame_angles:
            return self._frame_angles[key]
        speed_limit = 300.0
        target = max(-1.0, min(1.0, velocity_x / speed_limit)) * part.max_angle
        angle = self._springs.setdefault(key, _Spring()).step(target, dt)
        self._frame_angles[key] = angle
        return angle

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
        startle_progress: float | None = None,
        idle_fidget_progress: float | None = None,
        idle_fidget_side: str = "left",
        motion_velocity_x: float = 0.0,
        walk_seconds: float | None = None,
    ) -> pygame.Surface:
        now = time.monotonic()
        dt = 1.0 / 60.0 if self._last_compose_time is None else max(
            0.0, min(0.05, now - self._last_compose_time)
        )
        self._last_compose_time = now
        self._frame_angles.clear()
        idle = IDLE_CLIP.sample(seconds)
        walk = WALK_CLIP.sample(seconds if walk_seconds is None else walk_seconds)
        startle = (
            POKE_REACTION_CLIP.sample(
                max(0.0, min(1.0, startle_progress)) * POKE_REACTION_CLIP.duration
            )
            if startle_progress is not None
            else {}
        )
        ear_led_pulse = max(ear_led_pulse, startle.get("ear_led_pulse", 0.0))
        fidget = (
            IDLE_FIDGET_CLIP.sample(
                max(0.0, min(1.0, idle_fidget_progress))
                * IDLE_FIDGET_CLIP.duration
            )
            if idle_fidget_progress is not None
            else {}
        )
        if idle_fidget_side == "right":
            mirrored = {}
            for name, value in fidget.items():
                if name.endswith("_left"):
                    name = name[:-5] + "_right"
                elif name.endswith("_right"):
                    name = name[:-6] + "_left"
                mirrored[name] = value
            fidget = mirrored
        strength = max(0.0, min(1.0, walk_strength)) if walking else 0.0
        ear_angles: dict[str, float] = {}
        for side, flick in (
            ("left", ear_flick_left),
            ("right", ear_flick_right),
        ):
            ear = self.parts.get(f"ear_{side}")
            if ear is None:
                continue
            angle = idle[f"ear_{side}"] + self._spring_angle(
                f"ear_{side}", ear, motion_velocity_x, dt
            )
            angle += flick - 2.0 * max(-1.0, min(1.0, gaze_x))
            angle += startle.get(f"ear_{side}", 0.0)
            if jumping:
                angle += -3.0 if side == "left" else 3.0
            ear_angles[side] = angle

        canvas = pygame.Surface((self.width, self.height), pygame.SRCALPHA, 32)
        face = self._face_with_gaze(expression_surface, gaze_x, gaze_y)
        if gaze_x == 0.0 and gaze_y == 0.0:
            face = self._face_for(expression_surface)

        for name in self._part_order:
            part = self.parts[name]
            role, side = part.role, part.side
            foot_offset_x = 0.0
            foot_offset_y = 0.0
            if role == "ear_glow":
                intensity = max(0.0, min(1.0, ear_led_pulse))
                if intensity <= 0:
                    continue
                image, position = self._rotation(
                    part.image,
                    part.pivot,
                    part.origin,
                    ear_angles.get(part.side or "", 0.0),
                )
                glow = image.copy()
                glow.set_alpha(round(210 * intensity))
                canvas.blit(glow, position)
                continue

            if role in ("arm", "upper_arm") and walking:
                value = walk.get(f"arm_{side}", 0.0) * strength
                # Walking is authored motion; keep the inertial state from
                # accumulating invisibly while it has control of the limb.
                self._spring_angle(f"arm_{side}", part, 0.0, dt)
            elif role == "foot" and walking:
                value = walk.get(f"feet_{side}", 0.0) * strength
                direction = -1.0 if motion_velocity_x < 0.0 else 1.0
                foot_offset_x = walk.get(f"foot_stride_{side}", 0.0) * direction
                foot_offset_y = -walk.get(f"foot_lift_{side}", 0.0)
                self._spring_angle(name, part, 0.0, dt)
            elif role == "ear":
                value = ear_angles.get(side or "", 0.0)
            elif role in ("arm", "upper_arm"):
                value = idle[f"arm_{side}"] + self._spring_angle(
                    f"arm_{side}", part, motion_velocity_x, dt
                )
                value += startle.get(f"arm_{side}", 0.0)
                value += fidget.get(f"arm_{side}", 0.0)
                if jumping:
                    value += 5.0 if side == "left" else -5.0
            elif role == "foot":
                value = idle[f"feet_{side}"] + fidget.get(f"feet_{side}", 0.0)
                value += self._spring_angle(
                    name, part, motion_velocity_x, dt
                )
                foot_offset_y = -fidget.get(f"foot_lift_{side}", 0.0)
            elif role == "hair":
                value = self._spring_angle(name, part, motion_velocity_x, dt)
                if name.startswith("top_hair_"):
                    value += idle.get(f"hair_{side}", 0.0)
                if name.startswith(("top_hair_", "bottom_hair_")):
                    value += startle.get(f"hair_{side}", 0.0)
                    value += fidget.get(f"hair_{side}", 0.0)
            elif role == "ear_led":
                value = ear_angles.get(side or "", 0.0)
            else:
                value = 0.0

            if role == "static" or role == "hair_static" or role == "ear_anchor":
                if name == "faces":
                    canvas.blit(part.image, part.origin)
                elif name == "frame":
                    canvas.blit(part.image, part.origin)
                else:
                    canvas.blit(part.image, part.origin)
                if name == "frame":
                    canvas.blit(face, (0, 0))
                continue

            image, position = self._rotation(part.image, part.pivot, part.origin, value)
            if role == "foot" and walking:
                position = (
                    position[0] + round(foot_offset_x * strength),
                    position[1] + round(foot_offset_y * strength),
                )
            elif role == "foot" and foot_offset_y:
                position = (position[0], position[1] + round(foot_offset_y))
            canvas.blit(image, position)

        return canvas
