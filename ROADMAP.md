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

## Still open from Phases 0 and 1

| Item | Why | Effort |
|---|---|---|
| Hands-on look at the overlays by an animator | CI screenshots are blank under Xvfb, so appearance hasn't been inspected | S |
| Verify ghosts with NLA time mapping and the *seconds* display | Assumed, not tested | S |

## Phase 2 - Bigger tools

| Item | Notes | Effort |
|---|---|---|
| **Value lattice**: retime lattice gets top/bottom edges to scale values about a pivot (zero, first key, last key, centre) | Maya region/lattice tool, both axes | M |
| **2D region manipulator**: corner grips scale time and value together, middle drag moves | Maya Region Tool | M |
| **Tween / Breakdown slider** with live preview, built on the Simplify preview machinery (favour previous ↔ next, overshoot) *(Blender has Breakdown/Blend operators; this unifies them in one panel)* | Tween Machine | M |
| **Smooth with live preview** (Butterworth / Gaussian), same confirm/cancel pattern | Curves > Smooth | M |
| **Mocap cleanup workflow**: bake to every frame → simplify → Clamped tangents, as one button | Bake + Simplify | M |
| **Retime around the playhead / to N frames / presets** (×0.5, ×2, fit to marker range) | Scale Keys options | S |
| **Retime across the whole rig**, not only the visible curves (all channels of selected objects/bones) | Time Editor style | M |
| **Non-linear time warp**: a warp curve that eases timing in and out over a range | Time Editor / warp | L |

## Phase 3 - Polish and distribution

| Item | Notes | Effort |
|---|---|---|
| Documentation with GIFs per tool | Adoption | S |
| UI translations | - | M |
| Publish on extensions.blender.org | The platform does its own updates and doesn't allow self-updaters, so the GitHub updater must turn itself off when installed from the official repository (detect the repo's remote URL) | S |
| Theme-aware colours (ghost/lattice colours from the Graph Editor theme) | Fits dark/light themes | S |

## Suggested order

1. ~~Phase 0 test pass and fixes, shortcuts and pie menu~~ and ~~Phase 1 quick wins~~: done in v1.1.
2. Get v1.1 into an animator's hands and fix what they notice.
3. Value lattice and region manipulator (v1.2), since they reuse the retime lattice.
4. Tween and Smooth sliders on the live-preview pattern (v1.3).
