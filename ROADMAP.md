# Roadmap

What could come next, grouped by priority. Effort: **S** about a day, **M** a few days, **L** a week or more.
Items marked *(exists in Blender)* only need a one-click shortcut, because Blender already has the feature
buried in a menu.

## Done in 1.1.0 (Phase 0 and Phase 1)

* Real-GUI tests in CI: Blender 4.2 LTS and 5.1 under Xvfb, driven by `event_simulate`. These found two bugs:
  overlays drifted (up to 14 px) in 5.x, and loading saved ghosts crashed at startup. Headless tests run in CI too.
* Rebindable shortcuts per tool, checked against Blender's default keymap; tangent pie menu (Alt+V); optional
  tangent icons in the Graph Editor header.
* Retime: typed percentage in the lattice, Scale % field with Start / Center / End anchor.
* Simplify: large selections analysed in the background with a progress bar.
* Ghosts saved in the .blend; the "update installed" message survives the add-on reloading itself.
* Tangents: Break / Unify, In-only / Out-only (panel or Ctrl/Alt+click), default tangent for new keys.
* Curves tool: Pre/Post Infinity (Constant, Linear, Cycle, Cycle with Offset, Oscillate) and Euler filter.
* Key Stats tool: frame / value fields for the selection, absolute or relative, degrees for rotation.
* Ghost slots A/B/C with their own colours, scene-range sampling, dashed style.

## Done in 1.2.0 (Phase 2 and Phase 3)

* Region lattice: value edges, corners and move on top of the retime lattice; value scale % about zero / first /
  last / centre; x0.5 / x2, exact length, fit to preview range or markers, playhead anchor; whole-rig scope.
* Tween / breakdown slider with overshoot and key-at-playhead; Smooth with live preview (Gaussian-weighted line fit);
  Time Warp (ease in / out / in-out); one-click mocap cleanup. All share one live-preview slider framework.
* Docs with screenshots and GIFs recorded by the GUI tests; Russian and Spanish UI; theme-aware colours;
  updater steps aside for extensions.blender.org installs; Blender's extension validator runs in CI. It caught an
  over-long tagline that would have failed submission.
* Visual check from real screenshots led to new ghost colours (no longer confused with the blue Z channel) and
  sidebar labels that don't clip.

## Still open

| Item | Notes | Effort |
|---|---|---|
| Submit to extensions.blender.org | Prepared and validated; the submission itself is the maintainer's | S |
| An animator's hands-on feedback | Everything is tested, but feel is best judged by use | S |
| Verify ghosts with NLA time mapping and the *seconds* display | Assumed, not tested | S |
| Translate runtime-built strings (key counts) and more languages | Framework in `i18n.py` | S |
| Region lattice re-reads the display mapping during drags | Matters only with *Normalize* on | S |

## Suggested order

1. ~~Phases 0 and 1~~ (v1.1) and ~~Phases 2 and 3~~ (v1.2): done.
2. Get v1.2 into animators' hands, fix what they notice, then submit to extensions.blender.org.
