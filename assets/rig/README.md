# Illustrator part rig

The runtime uses transparent, aligned 446×910 images. `layers/` contains the
original layer composites, `sublayers/` contains the isolated Illustrator
objects, and `parts/` contains the independently animated body parts built from
those object exports. Pikita's shoulder panels, foreground arms, feet, ear
inserts, LEDs, and each separate hair shape have their own PNGs and pivots.

Press **R** to switch between the assembled rig and the original full PNG
sprite. The selection is saved in the ignored `settings.json` file.

## Regenerate the rig assets

1. Open the ignored `Pikita V4.ai` in Illustrator.
2. Choose **File → Scripts → Other Script** and run
   `tools/export_illustrator_sublayers.jsx`.
3. Run `python tools/build_rig_parts.py` to create `assets/rig/parts/`.
4. To rebuild eye tracking, also run `python tools/build_eye_tracking_assets.py`.

The Illustrator script exports a temporary copy of the artwork and closes it
without saving. It unlocks that copy before isolating any layers or objects,
including hidden locked sublayers, so Illustrator can change their visibility
during export. It keeps every PNG aligned to the artboard, writes masks as
white silhouettes, and exports pupil and glint artwork with clipped ancestor
masks temporarily disabled. The source Illustrator document is unchanged.

The eye builder requires those full, unmasked pupil and glint exports. The
application translates each eye's complete pupil-and-shine image, then applies
that eye's fixed aperture at its original position. This preserves the black
eye outline. The present tracked exports predate the unmasked-pupil flag, so
eye tracking stays disabled until the Illustrator script is run again.

## Motion

Part PNGs share a coordinate canvas and carry pivots in `parts/manifest.json`.
The renderer applies damped angular lag from horizontal drag and walking speed
to hair, ears, arms, and feet. Authored walking clips control arms and feet
while he is walking. Ear LEDs keep their original yellow fill, with a separate
soft blurred glow pass during attention flashes.
