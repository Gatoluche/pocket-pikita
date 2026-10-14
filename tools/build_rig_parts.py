"""Build aligned, independently animatable parts from Illustrator exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw


SIZE = (446, 910)
TOP_HAIR_PIVOTS = {
    "left": (190.0, 238.0),
    "right": (366.0, 278.0),
    "front": (246.0, 192.0),
}
BODY_SWING_PATHS = {
    "left": "item_00115_pathitem_unnamed.png",
    "right": "item_00122_pathitem_unnamed.png",
}
PIVOTS = {
    "body": (223.0, 594.0),
    "arm_left": (80.0, 594.0),
    "arm_right": (366.0, 594.0),
    "foot_left": (65.0, 867.0),
    "foot_right": (381.0, 867.0),
    "ear_left": (76.0, 258.0),
    "ear_right": (370.0, 258.0),
}


def load_aligned(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.size != SIZE:
        raise ValueError(f"{path} is {image.size}; expected {SIZE}")
    return image


def alpha_union(images: Iterable[Image.Image]) -> Image.Image:
    result = Image.new("L", SIZE, 0)
    for image in images:
        result = ImageChops.lighter(result, image.getchannel("A"))
    return result


def compose(images: Iterable[Image.Image]) -> Image.Image:
    result = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    for image in images:
        result.alpha_composite(image)
    return result


def item_index(entry: dict) -> int:
    filename = Path(entry["file"]).name
    try:
        return int(filename.split("_")[1])
    except (IndexError, ValueError):
        return 0


class PartBuilder:
    def __init__(self, rig_dir: Path, output_dir: Path):
        self.rig_dir = rig_dir
        self.sublayers_dir = rig_dir / "sublayers"
        self.output_dir = output_dir
        self.source_manifest = json.loads(
            (self.sublayers_dir / "manifest.json").read_text(encoding="utf-8")
        )
        canvas = tuple(self.source_manifest.get("canvas_size", ()))
        if canvas != SIZE:
            raise ValueError(f"Illustrator export canvas is {canvas}; expected {SIZE}")
        self.entries = self.source_manifest.get("object_exports", [])
        self.parts: dict[str, dict] = {}

    def layer(self, name: str) -> Image.Image:
        manifest = json.loads((self.rig_dir / "manifest.json").read_text(encoding="utf-8"))
        return load_aligned(self.rig_dir / "layers" / manifest["layer_files"][name])

    def objects(self, layer_path: list[str], group_path: list[str] | None = None) -> list[dict]:
        return [
            entry
            for entry in self.entries
            if entry.get("layer_path") == layer_path
            and (group_path is None or entry.get("group_path") == group_path)
            and entry.get("item_type") in ("PathItem", "CompoundPathItem")
        ]

    def image_for(self, entry: dict) -> Image.Image:
        return load_aligned(self.sublayers_dir / entry["file"])

    def find_named(self, layer_path: list[str], group_path: list[str], name: str) -> dict:
        matches = [
            entry
            for entry in self.entries
            if entry.get("layer_path") == layer_path
            and entry.get("group_path") == group_path
            and entry.get("item_name") == name
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one {name} export under {'/'.join(layer_path + group_path)}, "
                f"found {len(matches)}. Rerun the Illustrator exporter."
            )
        return matches[0]

    def save_part(
        self,
        name: str,
        image: Image.Image,
        pivot: tuple[float, float] = (0.0, 0.0),
        role: str = "static",
        side: str | None = None,
        max_angle: float = 0.0,
        z: int = 0,
        order: int = 0,
    ) -> None:
        if image.size != SIZE:
            raise ValueError(f"Part {name} uses {image.size}; expected {SIZE}")
        relative = f"{name}.png"
        image.save(self.output_dir / relative, optimize=True)
        self.parts[name] = {
            "file": relative,
            "pivot": [round(pivot[0], 2), round(pivot[1], 2)],
            "role": role,
            "side": side,
            "max_angle": max_angle,
            "z": z,
            "order": order,
        }

    def build_body_and_arms(self) -> None:
        body_entries = self.objects(["Body", "Darker"])
        by_name = {Path(entry["file"]).name: entry for entry in body_entries}
        if not all(name in by_name for name in BODY_SWING_PATHS.values()):
            raise ValueError("Could not locate both isolated shoulder panels in Body/Darker")

        side_panels = {
            side: self.image_for(by_name[filename])
            for side, filename in BODY_SWING_PATHS.items()
        }
        torso_objects = [
            self.image_for(entry)
            for entry in sorted(body_entries, key=item_index)
            if Path(entry["file"]).name not in BODY_SWING_PATHS.values()
        ]
        # Illustrator's pageItems collection is front-to-back for these body
        # shapes; preserve their observed export order for the static torso.
        torso = compose(torso_objects)
        self.save_part(
            "body", torso, PIVOTS["body"], role="torso", max_angle=1.4, z=20
        )
        for side, image in side_panels.items():
            self.save_part(
                f"upper_arm_{side}", image, PIVOTS[f"arm_{side}"],
                role="upper_arm", side=side, max_angle=4.0, z=10,
            )

        for side in ("left", "right"):
            group = ["Left Arm"] if side == "left" else ["Right Arm"]
            arm_entries = self.objects(["Arms", "Darker"], group)
            if len(arm_entries) < 4:
                raise ValueError(f"Expected isolated pieces for the {side} arm")
            arm = compose(self.image_for(entry) for entry in sorted(arm_entries, key=item_index))
            self.save_part(
                f"arm_{side}", arm, PIVOTS[f"arm_{side}"],
                role="arm", side=side, max_angle=4.0, z=70,
            )

    def build_feet(self) -> None:
        groups = self.source_manifest.get("group_exports", [])
        for side, label in (("left", "Left Foot"), ("right", "Right Foot")):
            matches = [
                entry
                for entry in groups
                if entry.get("layer_path") == ["Feet", "Base"]
                and entry.get("group_path") == [label]
            ]
            if len(matches) != 1:
                raise ValueError(f"Expected one isolated {label} group export")
            image = load_aligned(self.sublayers_dir / matches[0]["file"])
            self.save_part(
                f"foot_{side}", image, PIVOTS[f"foot_{side}"],
                role="foot", side=side, max_angle=2.5, z=0,
            )

    def build_ears(self) -> None:
        ear_entries = [
            entry for entry in self.entries
            if entry.get("layer_path") == ["Ear", "Ears"]
            and entry.get("item_name") in ("Ear", "LED")
        ]
        if len(ear_entries) != 4:
            raise ValueError("Expected two isolated ear shapes and two LED shapes")
        for side in ("left", "right"):
            pivot = PIVOTS[f"ear_{side}"]
            side_entries = []
            for entry in ear_entries:
                image = self.image_for(entry)
                bounds = image.getchannel("A").getbbox()
                if bounds and ((bounds[0] + bounds[2]) / 2 < SIZE[0] / 2) == (side == "left"):
                    side_entries.append((entry, image))
            ears = [image for entry, image in side_entries if entry["item_name"] == "Ear"]
            leds = [image for entry, image in side_entries if entry["item_name"] == "LED"]
            if len(ears) != 1 or len(leds) != 1:
                raise ValueError(f"Could not isolate both pieces for the {side} ear")
            ear, led = ears[0], leds[0]
            self.save_part(
                f"ear_{side}", ear, pivot, role="ear", side=side,
                max_angle=3.5, z=35,
            )
            self.save_part(
                f"ear_led_{side}", led, pivot, role="ear_led", side=side,
                max_angle=3.5, z=37,
            )

            # Keep a small fixed patch at the hinge above the moving shape.
            # The source art supplies the exact outline and fill at the root.
            patch_mask = Image.new("L", SIZE, 0)
            draw = ImageDraw.Draw(patch_mask)
            px, py = pivot
            radius_x, radius_y = 13, 15
            draw.ellipse((px - radius_x, py - radius_y, px + radius_x, py + radius_y), fill=255)
            patch = Image.new("RGBA", SIZE, (0, 0, 0, 0))
            patch.paste(ear, (0, 0), patch_mask)
            self.save_part(
                f"ear_anchor_{side}", patch, role="ear_anchor", side=side, z=38,
            )

    @staticmethod
    def hair_pivot(image: Image.Image, side: str) -> tuple[float, float]:
        bounds = image.getchannel("A").getbbox()
        if bounds is None:
            return SIZE[0] / 2, SIZE[1] / 2
        left, top, right, bottom = bounds
        if side == "left":
            x = right - 7
        elif side == "right":
            x = left + 7
        else:
            x = (left + right) / 2
        return float(x), float(bottom - 8)

    def build_hair(self, layer_name: str, prefix: str, z: int) -> list[str]:
        layer_path = [layer_name]
        entries = self.objects(layer_path)
        if not entries:
            raise ValueError(f"No individual {layer_name} objects were exported")
        source = self.layer(layer_name)
        surfaces = [(entry, self.image_for(entry)) for entry in entries]
        union = alpha_union(image for entry, image in surfaces)
        residual_alpha = source.getchannel("A")
        # Isolated objects are reintroduced individually; remove their original
        # pixels from the static layer so nothing is double drawn.
        residual_alpha = ImageChops.multiply(
            residual_alpha, union.point(lambda value: 0 if value else 255)
        )
        residual = source.copy()
        residual.putalpha(residual_alpha)
        self.save_part(f"{prefix}_static", residual, role="hair_static", z=z, order=0)

        names: list[str] = []
        ordered = sorted(surfaces, key=lambda pair: item_index(pair[0]), reverse=True)
        for order, (entry, image) in enumerate(ordered, 1):
            bounds = image.getchannel("A").getbbox()
            if bounds is None:
                continue
            center_x = (bounds[0] + bounds[2]) / 2
            side = "left" if center_x < 205 else "right" if center_x > 241 else "center"
            if layer_name == "Top Hair":
                side = "left" if center_x < 190 else "right" if center_x > 310 else "front"
                pivot = TOP_HAIR_PIVOTS[side]
                max_angle = 2.0 if side == "front" else 3.0
            else:
                pivot = self.hair_pivot(image, side)
                max_angle = 1.5 if side == "center" else 2.0
            key = f"{prefix}_{item_index(entry):05d}"
            self.save_part(
                key, image, pivot, role="hair", side=side,
                max_angle=max_angle, z=z, order=order,
            )
            names.append(key)
        return names

    def build(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.build_feet()
        self.build_body_and_arms()
        self.build_ears()
        bottom_hair = self.build_hair("Bottom Hair", "bottom_hair", z=30)
        top_hair = self.build_hair("Top Hair", "top_hair", z=90)

        face_manifest = json.loads((self.rig_dir / "manifest.json").read_text(encoding="utf-8"))
        layer_files = face_manifest["layer_files"]
        for z, layer_name, key in (
            (40, "Faces", "faces"), (50, "Frame", "frame"),
        ):
            self.save_part(
                key,
                load_aligned(self.rig_dir / "layers" / layer_files[layer_name]),
                (223.0, 543.0),
                role="head",
                max_angle=1.2,
                z=z,
            )

        order = [
            *[name for name in self.parts if self.parts[name]["role"] == "foot"],
            *[name for name in self.parts if self.parts[name]["role"] == "upper_arm"],
            "body",
            "bottom_hair_static",
            *bottom_hair,
            "ear_left", "ear_right",
            "ear_led_left", "ear_led_right",
            "ear_anchor_left", "ear_anchor_right",
            "faces", "frame",
            "arm_left", "arm_right",
            "top_hair_static",
            *top_hair,
        ]
        manifest = {
            "canvas_size": list(SIZE),
            "source_manifest": "../sublayers/manifest.json",
            "parts": self.parts,
            "draw_order": order,
            "eyes": {
                "source": "assets/rig/eyes",
                "tracking_enabled_only_when_unmasked_export_is_verified": True,
            },
            "physics": {
                "description": "Damped angular and positional lag follows two-dimensional motion.",
                "max_speed_px_s": 450.0,
            },
        }
        (self.output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rig", type=Path, default=Path("assets/rig"))
    parser.add_argument("--output", type=Path, default=Path("assets/rig/parts"))
    args = parser.parse_args()
    PartBuilder(args.rig, args.output).build()


if __name__ == "__main__":
    main()
