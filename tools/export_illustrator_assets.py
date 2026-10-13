"""Export top-level PDF-compatible Illustrator layers as aligned PNGs.

Requires pypdf, Pillow, NumPy, and Poppler's pdftoppm executable. The active
top-level Illustrator layer visibility is ignored: each PDF optional-content
group is rendered on its own against a temporary magenta matte. Illustrator
sublayers are not PDF optional-content groups and remain composited together;
use export_illustrator_sublayers.jsx for those.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject


DEFAULT_PIVOTS = {
    "Feet": {"left": [65, 867], "right": [381, 867]},
    "Ear": {"left": [76, 258], "right": [370, 258]},
    "Arms": {"left": [80, 594], "right": [366, 594]},
}


def safe_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def rasterize_layer(
    source: Path,
    name: str,
    output_stem: Path,
    pdftoppm: Path,
    dpi: int,
) -> Image.Image:
    reader = PdfReader(str(source))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    optional_content = writer._root_object["/OCProperties"]
    groups = list(optional_content["/OCGs"])
    selected = next(
        group for group in groups if str(group.get_object()["/Name"]) == name
    )
    configuration = optional_content["/D"]
    configuration[NameObject("/BaseState")] = NameObject("/OFF")
    configuration[NameObject("/ON")] = ArrayObject([selected])
    configuration[NameObject("/OFF")] = ArrayObject(
        [group for group in groups if group != selected]
    )

    page = writer.pages[0]
    left, bottom = map(float, page.mediabox.lower_left)
    width, height = map(float, (page.mediabox.width, page.mediabox.height))
    background = (
        f"q 1 0 1 rg {left:g} {bottom:g} {width:g} {height:g} re f Q\n"
    ).encode("ascii")
    content = DecodedStreamObject()
    content.set_data(background + page.get_contents().get_data())
    page[NameObject("/Contents")] = writer._add_object(content)

    pdf_path = output_stem.with_suffix(".pdf")
    png_stem = output_stem
    with pdf_path.open("wb") as stream:
        writer.write(stream)
    subprocess.run(
        [
            str(pdftoppm),
            "-f",
            "1",
            "-l",
            "1",
            "-r",
            str(dpi),
            "-png",
            "-singlefile",
            str(pdf_path),
            str(png_stem),
        ],
        check=True,
        capture_output=True,
    )
    return unmatte(png_stem.with_suffix(".png"))


def unmatte(path: Path) -> Image.Image:
    """Convert a magenta-matte raster to straight-alpha RGBA."""
    pixels = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    matte = np.array([255.0, 0.0, 255.0], dtype=np.float32)
    alpha = np.max(np.abs(pixels - matte), axis=2) / 255.0
    alpha[alpha < (1.5 / 255.0)] = 0.0

    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    visible = alpha > 0
    straight = np.zeros_like(pixels)
    straight[visible] = (
        pixels[visible] - matte * (1.0 - alpha[visible, None])
    ) / alpha[visible, None]
    rgba[:, :, :3] = np.clip(straight, 0, 255).round().astype(np.uint8)
    rgba[:, :, 3] = np.clip(alpha * 255, 0, 255).round().astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="PDF-compatible .ai source file")
    parser.add_argument(
        "--output",
        type=Path,
        help="Layer output folder (defaults to assets/rig/layers beside the source)",
    )
    parser.add_argument(
        "--pdftoppm",
        type=Path,
        help="Path to Poppler pdftoppm (defaults to searching PATH)",
    )
    parser.add_argument("--dpi", type=int, default=96)
    args = parser.parse_args()

    source = args.source.resolve()
    output = (args.output or source.parent / "assets" / "rig" / "layers").resolve()
    base_sprite = source.parent / "assets" / "Base.png"
    if not base_sprite.is_file():
        raise FileNotFoundError(f"Could not find the alignment sprite: {base_sprite}")

    pdftoppm = args.pdftoppm
    if pdftoppm is None:
        from shutil import which

        executable = which("pdftoppm")
        if executable is None:
            raise FileNotFoundError("Poppler pdftoppm was not found; pass --pdftoppm")
        pdftoppm = Path(executable)
    pdftoppm = pdftoppm.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    reader = PdfReader(str(source))
    groups = reader.trailer["/Root"]["/OCProperties"]["/OCGs"]
    names = [str(group.get_object()["/Name"]) for group in groups]
    target_size = Image.open(base_sprite).size
    output.mkdir(parents=True, exist_ok=True)

    layers: dict[str, Image.Image] = {}
    with tempfile.TemporaryDirectory(prefix="pikita-layer-export-") as temp_dir:
        temporary = Path(temp_dir)
        for index, name in enumerate(names):
            raster = rasterize_layer(
                source,
                name,
                temporary / f"{index:02d}_{safe_name(name)}",
                pdftoppm,
                args.dpi,
            )
            layers[name] = raster

    assembled = Image.new("RGBA", layers[names[0]].size, (0, 0, 0, 0))
    for name in names:
        assembled.alpha_composite(layers[name])
    bounds = assembled.getbbox()
    if bounds is None:
        raise ValueError("No visible artwork was found in the Illustrator layers")

    exported: dict[str, str] = {}
    empty: list[str] = []
    for name in names:
        layer = layers[name].crop(bounds).resize(target_size, Image.Resampling.LANCZOS)
        if layer.getbbox() is None:
            empty.append(name)
            continue
        filename = f"{safe_name(name)}.png"
        layer.save(output / filename, optimize=True)
        exported[name] = filename

    manifest = {
        "canvas_size": list(target_size),
        "source_file": source.name,
        "raster_dpi": args.dpi,
        "source_crop_bounds": list(bounds),
        "export_scope": "PDF optional-content groups (top-level Illustrator layers)",
        "nested_sublayers": "Composited together; use export_illustrator_sublayers.jsx to export visible sublayers.",
        "source_layer_order_back_to_front": names,
        "layer_files": exported,
        "empty_layers": empty,
        "paired_layer_pivots": DEFAULT_PIVOTS,
    }
    (output.parent / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Exported {len(exported)} layers to {output}")
    print(f"Canvas: {target_size[0]} x {target_size[1]} px; source crop: {bounds}")
    print(f"Empty layers: {', '.join(empty) if empty else 'none'}")


if __name__ == "__main__":
    main()
