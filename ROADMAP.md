# Pikita development roadmap

## Current: independent sprite rig

- Export each movable body part as an aligned transparent PNG with a named
  pivot: hair pieces, ears and LEDs, shoulder panels, arms, and feet.
- Keep the Illustrator export reproducible and preserve the source document.
- Apply damped inertia to parts while Pikita is dragged or moves around.
- Export complete pupil disks and shines, then clip each moving eye to its
  fixed eye aperture inside the application.
- Keep the ear roots covered while they move; derive a soft LED bloom from the
  emitter pixels and composite it over the ear fill.

## Implemented: drag toss and screen-edge impact

- A fast release carries smoothed cursor velocity into Pikita as a bounded,
  damped toss.
- The visible sprite stays within its monitor, rebounds on impact, and plays a
  speed-sensitive synthesized electronic bump. Impacts add a brief squash and
  rebound along the collision axis.
- Other desktop windows are not collision surfaces yet.

## Implemented: tactile poke response

- A click still gets a short expression and squeak response, with a quick
  authored recoil through the separate ears, arms, and hair before he settles.
- His ear LEDs flash with the recoil, then fade back to their normal color.

## Implemented: occasional idle fidget

- Pikita rests without a constant body-part sway. Every so often, one floating
  foot lifts and settles with a small counter-movement in his folded arms and
  hair; the fidget side alternates.

## Implemented: floating-foot walk

- One detached foot swings forward and lifts while the other trails and settles;
  the folded torso and arms stay still so the alternating steps read clearly.

## Later: authored animation and attention

- Expand the clip library with richer startled reactions and transitions
  between expressions.
- Add more attention sources after cursor tracking: sound-producing windows,
  Windows notifications, and sudden screen color changes.
- Add sound design and personality-driven reactions that support ordinary
  desktop-pet use without requiring an extra control window.
