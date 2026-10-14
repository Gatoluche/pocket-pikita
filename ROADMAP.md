# Pikita development roadmap

## Current: independent sprite rig

- Export each movable body part as an aligned transparent PNG with a named
  pivot: hair pieces, ears and LEDs, shoulder panels, arms, and feet.
- Keep the Illustrator export reproducible and preserve the source document.
- Apply damped inertia to parts while Pikita is dragged or moves around. Let
  authored walk clips control his arms and feet during a walk.
- Keep the walking cycle phase tied to each walk, with small alternating foot
  steps and only a restrained counter-motion in his folded arms.
- Export complete pupil disks and shines, then clip each moving eye to its
  fixed eye aperture inside the application.
- Keep the ear roots covered while they move; derive a soft LED bloom from the
  emitter pixels and composite it over the ear fill.

## Implemented: drag toss and screen-edge impact

- A fast release carries smoothed cursor velocity into Pikita as a bounded,
  damped toss.
- The visible sprite stays within its monitor, rebounds on impact, and plays a
  speed-sensitive synthesized electronic bump.
- Other desktop windows are not collision surfaces yet.

## Later: authored animation and attention

- Build reusable clips from separate parts for glances, ear reactions,
  fidgets, startled reactions, and transitions between expressions.
- Add more attention sources after cursor tracking: sound-producing windows,
  Windows notifications, and sudden screen color changes.
- Add sound design and personality-driven reactions that support ordinary
  desktop-pet use without requiring an extra control window.
