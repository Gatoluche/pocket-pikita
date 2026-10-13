# Illustrator rig experiment

`layers/` contains transparent, 446×910 exports of the top-level groups in the
PDF-compatible Illustrator file. All images use the same character-space canvas,
so their pixels stay aligned when the renderer composes them. The PDF view only
exposes top-level groups; nested Illustrator sublayers such as eye-expression
spares are composited together in these exports.

The renderer assembles the body, hair, ears, arms, and feet from these parts. It
uses the existing `assets/*.png` sprites for facial expressions, including the
cheek patches. The saved face visibility in the Illustrator document is not
used to choose a base expression. Press **R** to switch between the assembled
rig and the original full PNG sprite; the choice is saved in `settings.json`.

To regenerate the top-level exports, install `pypdf`, `Pillow`, and `NumPy`,
then run `tools/export_illustrator_assets.py` with the local, ignored source
file. The exporter also needs Poppler's `pdftoppm`; pass its path with
`--pdftoppm` when it is not on `PATH`. It renders each PDF layer separately,
so the Illustrator document's saved visibility configuration does not affect
these top-level exports.

To export visible nested layers separately, open the source file in Illustrator
and choose **File → Scripts → Other Script**, then select
`tools/export_illustrator_sublayers.jsx`. The script is designed to export
each visible layer and sublayer to aligned 446×910 transparent PNGs under
`assets/rig/sublayers/`, with a manifest of source layer paths. It opens a
temporary copy and closes it without saving, so it does not change the source
document. This Illustrator script has not yet been run in this session.
