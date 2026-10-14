# Pikita development roadmap

## Current: independent sprite rig

- Export each movable body part as an aligned transparent PNG with a named
  pivot: hair pieces, ears and LEDs, shoulder panels, arms, and feet.
- Keep the Illustrator export reproducible and preserve the source document.
- Export complete pupil disks and shines, then clip each moving eye to its
  fixed eye aperture inside the application.
- Keep the ear roots covered while they move. The ear LEDs keep their normal
  appearance without a flash effect.

## Implemented: drag toss and screen-edge impact

- A fast release carries smoothed cursor velocity into Pikita as a bounded,
  damped toss.
- The visible sprite stays inside the outer edges of the joined display layout,
  crosses between touching monitors, and slows under gravity and air drag.
- Screen impacts play a speed-sensitive synthesized electronic bump and add a
  brief squash along the collision axis.
- The hair strands, ears, arms, feet, torso, and head lag in two dimensions
  during drags, tosses, walks, and jumps; the torso and head move more subtly.
- Dragging keeps the clicked point anchored and computes body rotation from
  cursor acceleration and the anchor's lever arm.
- Other desktop windows are not collision surfaces yet.

## Implemented: tactile poke response

- A click still gets a short expression and squeak response, with a quick
  authored recoil through the separate ears, arms, and hair before he settles.

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
