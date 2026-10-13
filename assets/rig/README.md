# Illustrator rig experiment

`layers/` contains transparent, 446×910 exports of the named groups in the
PDF-compatible Illustrator file. All images use the same character-space canvas,
so their pixels stay aligned when the renderer composes them.

The renderer assembles the body, hair, ears, arms, and feet from these parts. It
uses the existing `assets/*.png` sprites for facial expressions, including the
cheek patches. The saved face visibility in the Illustrator document is not
used to choose a base expression. Press **R** to switch between the assembled
rig and the original full PNG sprite; the choice is saved in `settings.json`.

To regenerate the layer exports, install `pypdf`, `Pillow`, and `NumPy`, then
run `tools/export_illustrator_assets.py` with the local, ignored source file.
The exporter also needs Poppler's `pdftoppm`; pass its path with `--pdftoppm`
when it is not on `PATH`. It renders each Illustrator layer separately, so the
source document's current visibility configuration does not affect the export.
