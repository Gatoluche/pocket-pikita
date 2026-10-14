"""Build aligned eye-tracking PNGs from Illustrator object exports.

The canonical Base sprite supplies the expression and eye-fill color. The
separated Illustrator pupil and glint objects supply the movable artwork.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops


CANVAS_SIZE = (446, 910)
EYE_SOURCES = {
    "left": ["Eyes", "Angy", "Left"],
    "right": ["Eyes", "Angy", "Right"],
}


def object_export(
    manifest: dict,
    layer_path: list[str],
    item_name: str,
    group_path: list[str] | None = None,
) -> dict:
    if group_path is None:
        group_path = ["Pupil"]
    matches = [
        entry
        for entry in manifest.get("object_exports", [])
        if entry.get("layer_path") == layer_path
        and entry.get("group_path") == group_path
        and entry.get("item_name") == item_name
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one {item_name} export under {'/'.join(layer_path)}, "
            f"found {len(matches)}"
        )
    return matches[0]


def aligned_image(path: Path, expected_size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.size != expected_size:
        raise ValueError(f"{path} is {image.size}, expected {expected_size}")
    if image.getchannel("A").getbbox() is None:
        raise ValueError(f"{path} contains no visible artwork")
    return image


def eye_fill_color(
    base: Image.Image,
    pupil_art: Image.Image,
    side: str,
) -> tuple[int, int, int]:
    """Find the solid cyan eye fill beside each exported pupil."""
    bounds = pupil_art.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"The {side} pupil export is empty")
    left, top, right, bottom = bounds
    region = (
        max(0, left - 42),
        max(0, top + 4),
        min(base.width, right + 42),
        min(base.height, bottom + 24),
    )
    base_pixels = base.load()
    mask_pixels = pupil_art.getchannel("A").load()
    colors = Counter()
    for y in range(region[1], region[3]):
        for x in range(region[0], region[2]):
            r, g, b, a = base_pixels[x, y]
            if (
                a == 255
                and mask_pixels[x, y] == 0
                and r < 100
                and g > 200
                and b > 200
            ):
                colors[(r, g, b)] += 1
    if not colors:
        raise ValueError(f"Could not find cyan eye fill beside the {side} pupil")
    return colors.most_common(1)[0][0]


def build_assets(base_path: Path, sublayers_dir: Path, output_dir: Path) -> None:
    manifest_path = sublayers_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_size = tuple(manifest.get("canvas_size", ()))
    if expected_size != CANVAS_SIZE:
        raise ValueError(
            f"Illustrator exports use {expected_size}, expected {CANVAS_SIZE}"
        )

    base = Image.open(base_path).convert("RGBA")
    if base.size != expected_size:
        raise ValueError(f"{base_path} is {base.size}, expected {expected_size}")

    pupils = Image.new("RGBA", expected_size, (0, 0, 0, 0))
    eye_clip = Image.new("L", expected_size, 0)
    eye_clips: dict[str, Image.Image] = {}
    eye_colors: dict[str, tuple[int, int, int]] = {}
    pupil_images: dict[str, Image.Image] = {}
    for side, layer_path in EYE_SOURCES.items():
        pupil_entry = object_export(manifest, layer_path, "Pupil")
        glint_entry = object_export(manifest, layer_path, "Glint")
        clip_entry = object_export(manifest, layer_path, "Mask")
        if pupil_entry.get("is_unmasked_pupil") is not True:
            raise ValueError(
                f"The {side} pupil was not exported without Illustrator's mask; "
                "rerun tools/export_illustrator_sublayers.jsx"
            )
        if glint_entry.get("is_unmasked_pupil") is not True:
            raise ValueError(
                f"The {side} glint was not exported without Illustrator's mask; "
                "rerun tools/export_illustrator_sublayers.jsx"
            )
        pupil_art = aligned_image(sublayers_dir / pupil_entry["file"], expected_size)
        glint_art = aligned_image(sublayers_dir / glint_entry["file"], expected_size)
        if clip_entry.get("is_clip_mask") is not True:
            raise ValueError(
                f"The {side} eye Mask export is not marked as an Illustrator clipping path; "
                "rerun tools/export_illustrator_sublayers.jsx"
            )
        clip_art = aligned_image(sublayers_dir / clip_entry["file"], expected_size)
        side_pupils = Image.new("RGBA", expected_size, (0, 0, 0, 0))
        side_pupils.alpha_composite(pupil_art)
        side_pupils.alpha_composite(glint_art)
        pupils.alpha_composite(side_pupils)
        pupil_images[side] = side_pupils
        eye_colors[side] = eye_fill_color(base, pupil_art, side)
        side_clip = clip_art.getchannel("A")
        eye_clips[side] = side_clip
        eye_clip = ImageChops.lighter(eye_clip, side_clip)

    # Keep pupil art unmasked until runtime. Apply the fixed aperture after
    # translating the pupils so the clip stays aligned to the eye.
    pupil_fill = Image.new("RGBA", expected_size, (0, 0, 0, 0))
    fill_pixels = pupil_fill.load()
    for side, pupil_art in pupil_images.items():
        clipped_source_alpha = ImageChops.multiply(
            pupil_art.getchannel("A"), eye_clips[side]
        )
        pupil_alpha = clipped_source_alpha.load()
        bounds = pupil_art.getchannel("A").getbbox()
        assert bounds is not None
        for y in range(bounds[1], bounds[3]):
            for x in range(bounds[0], bounds[2]):
                if pupil_alpha[x, y]:
                    # Erase the source-position pupil inside its eye aperture;
                    # the fixed black outline sits outside this Illustrator mask.
                    fill_pixels[x, y] = (*eye_colors[side], 255)

    output_dir.mkdir(parents=True, exist_ok=True)
    clip_layer = Image.new("RGBA", expected_size, (255, 255, 255, 0))
    clip_layer.putalpha(eye_clip)
    clip_layer.save(output_dir / "pupil_clip.png", optimize=True)
    for side in ("left", "right"):
        single_clip = Image.new("RGBA", expected_size, (255, 255, 255, 0))
        single_clip.putalpha(eye_clips[side])
        single_clip.save(output_dir / f"pupil_clip_{side}.png", optimize=True)
        pupil_images[side].save(output_dir / f"pupils_{side}.png", optimize=True)
    pupil_fill.save(output_dir / "pupil_fill.png", optimize=True)
    pupils.save(output_dir / "pupils.png", optimize=True)
    metadata = {
        "canvas_size": list(expected_size),
        "base_sprite": str(base_path),
        "pupil_source_layers": EYE_SOURCES,
        "eye_fill_colors": {side: list(color) for side, color in eye_colors.items()},
        "pupil_components": ["Pupil", "Glint"],
        "unmasked_pupils": True,
        "pupil_clip_source": "filled Illustrator Pupil/Mask clipping paths",
        "pupil_clip_expression": "Angry",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("assets/Base.png"),
        help="Canonical aligned face sprite",
    )
    parser.add_argument(
        "--sublayers",
        type=Path,
        default=Path("assets/rig/sublayers"),
        help="Folder containing the Illustrator sublayer manifest and object PNGs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/rig/eyes"),
        help="Destination for the aligned eye-tracking PNGs",
    )
    args = parser.parse_args()

    build_assets(args.base, args.sublayers, args.output)


if __name__ == "__main__":
    main()
