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

To export visible nested layers and artwork groups separately, open the source
file in Illustrator and choose **File → Scripts → Other Script**, then select
`tools/export_illustrator_sublayers.jsx`. It writes aligned 446×910 transparent
PNGs under `assets/rig/sublayers/`, group-level exports under `groups/`, and
individual Illustrator objects under `objects/`. Each object export is
isolated from its siblings and keeps its aligned position on the 446×910
canvas. `manifest.json` records the Illustrator layer path, group path, object
type, and output file. The script opens a temporary copy and closes it without
saving, so it does not change the source document. It temporarily unlocks
visible source artwork and its parent layers in that copy so it can isolate
locked parts during export.

The first run produced fully transparent images for the nested layer entries.
The updated exporter records ancestry while walking the layer tree, excludes
artwork on parent layers from nested-layer exports, and exports individual
visible artwork objects. These object PNGs can split eye glints and hair blocks
when they are separate Illustrator objects. Rerun the script in Illustrator
to regenerate the exports and manifest; this cannot be done from the command
line because Illustrator must rasterize the document.
