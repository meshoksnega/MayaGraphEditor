# Roadmap

What could come next, grouped by priority. Effort: **S** about a day, **M** a few days, **L** a week or more.
Items marked *(exists in Blender)* only need a one-click shortcut, because Blender already has the feature
buried in a menu.

## Phase 0 - Make what exists solid (do first)

The drawing and mouse-driven parts of v1.0 were written without a live Blender window. Before adding features:

| Item | Why | Effort |
|---|---|---|
| Hands-on test pass in Blender 4.2 LTS and 5.x | Ghost overlay, simplify HUD, retime lattice and modal events are untested in real use | S |
| GUI tests in CI: GUI Blender under Xvfb, driven by `Window.event_simulate` (`--enable-event-simulate`) | Catches regressions in the modal tools automatically | M |
| Headless tests in CI on every push (`pip install bpy`) | The existing test suites, run automatically | S |
| Keyboard shortcuts (add-on keymap, rebindable) for tangents, snapshot/swap, simplify, retime | Maya users work from hotkeys | S |
| Tangent pie menu (one hotkey, six directions) | Even faster than the sidebar | S |
| Optional compact tangent row in the Graph Editor header | "Toolbar" that's visible without the sidebar | S |
| Retime: type an exact scale % or target length while dragging | Precision | S |
| Simplify: plan in the background with a progress bar | Removes the pause on thousands of keys | M |
| Save ghosts in the .blend (custom property on the action) | Buffers survive save/reopen | S |
| Show the "update installed" message again after the add-on reloads itself | The status is currently lost on reload | S |

## Phase 1 - Quick Maya-parity wins

| Item | Maya equivalent | Effort |
|---|---|---|
| **Break / Unify tangents** buttons (FREE vs ALIGNED handles) | Keys > Break / Unify Tangents | S |
| **In-only / Out-only** tangent application (modifier click) | In Tangent / Out Tangent menus | S |
| **Pre/Post Infinity** one-click: Constant, Linear, Cycle, Cycle with Offset, Oscillate (Cycles modifier + extrapolation) *(exists in Blender)* | Curves > Pre/Post Infinity | S |
| **Euler filter** button *(exists in Blender: Discontinuity Filter)* | Curves > Euler Filter | S |
| **Stats fields**: time and value boxes for the selection, absolute or relative offset across many keys | Graph Editor stats/value boxes | M |
| **Default tangent for new keys** dropdown in the Maya tab (Blender preference) | Default In/Out Tangent | S |
| **Multiple ghost slots** (A/B/C), each with its own colour | Several buffer curves | S |
| Ghost **"from current frame range"** option and dashed-line style | - | S |

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

1. Phase 0 test pass and fixes, then shortcuts and pie menu (gets the v1 tools into daily use).
2. Release v1.1 with the Phase 1 quick wins: Break/Unify, Infinity, Euler filter, ghost slots.
3. Value lattice and region manipulator (v1.2), since they reuse the retime lattice.
4. Tween and Smooth sliders on the live-preview pattern (v1.3).
