# Pikita development roadmap

## Current: independent sprite rig

- Export each movable body part as an aligned transparent PNG with a named
  pivot: hair pieces, ears and LEDs, shoulder panels, arms, and feet.
- Keep the Illustrator export reproducible and preserve the source document.
- Apply damped inertia to parts while Pikita is dragged or moves around. Let
  authored walk clips control his arms and feet during a walk.
- Export complete pupil disks and shines, then clip each moving eye to its
  fixed eye aperture inside the application.
- Keep the ear roots covered while they move and use a soft bloom pass for LED
  flashes.

## Next: tossed movement and impact response

- Carry measured cursor velocity into Pikita when a drag ends, so a fast
  release tosses him across the desktop.
- Integrate the toss with a bounded, damped physics model and detect impacts
  against desktop or monitor edges (and other supported obstacles).
- Play an impact sound when he hits something; choose its volume and pitch from
  the impact speed, then settle or rebound him in a controlled way.

## Later: authored animation and attention

- Build reusable clips from separate parts for glances, ear reactions,
  fidgets, startled reactions, and transitions between expressions.
- Add more attention sources after cursor tracking: sound-producing windows,
  Windows notifications, and sudden screen color changes.
- Add sound design and personality-driven reactions that support ordinary
  desktop-pet use without requiring an extra control window.
