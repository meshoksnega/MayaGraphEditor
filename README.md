# Maya Graph Editor Tools for Blender

Four Maya-style comforts for Blender's **Graph Editor**, in one add-on. Everything lives in the Graph Editor
sidebar (**N → Maya** tab). No new windows, no node graph, nothing that touches rendering or export.

| | Tool | What it does |
|---|---|---|
| 1 | **Buffer / Ghost Curve** | Snapshot a curve, keep editing, and see the snapshot as a faint overlay on the real curve. |
| 2 | **One-Click Tangents** | Spline · Linear · Flat · Stepped · Plateau · Clamped, one button each, applied to the selected keys. |
| 3 | **Simplify (live preview)** | Move the mouse / drag a slider to see the curve lose keys in real time. Confirm or cancel. |
| 4 | **Retiming Lattice** | Drag an edge of a lattice around the selected keys to stretch/compress them in time, across curves. |

Each tool can be switched off independently (**Preferences → Add-ons → Maya Graph Editor Tools**, or the
collapsed *Enabled Tools* panel at the bottom of the Maya tab). A disabled tool is fully unregistered:
no operators, no panel, no draw handler.

## Install

Requires **Blender 4.2 or newer** (developed against 5.1).

```bash
python3 build.py     # writes dist/maya_graph_editor-1.0.0.zip (+ a -legacy.zip)
```

* **Blender 4.2+:** Preferences → Get Extensions → ⌄ menu → *Install from Disk…* → pick
  `maya_graph_editor-1.0.0.zip`.
* Legacy add-on install (Preferences → Add-ons → Install from Disk) → use the `-legacy.zip`.

## Using the tools

### 1. Buffer / Ghost Curve
* **Snapshot** stores the shape of the selected curves (all visible curves if none is selected).
* The ghost is only drawn on top of the Graph Editor, so it can't be selected or get in the way of editing.
  Colour, opacity and line width are adjustable.
* **Clear** removes all ghosts.
* **Swap** (Maya's "swap buffer curve"): the curve returns to the snapshot shape and the shape it had becomes
  the new ghost, so you can A/B two versions.
* Ghosts live in memory for the session (they are not saved in the .blend). Blender's built-in ghost icon in
  the Graph Editor header also exists; this one adds colour control, per-curve buffers and Swap.

### 2. One-Click Tangents (applied to selected keyframes)

| Button | Blender equivalent |
|---|---|
| Spline | Automatic handles, Bezier (can overshoot, like Maya spline) |
| Clamped | Auto-clamped handles, Bezier (no overshoot) |
| Linear | Linear interpolation |
| Flat | Horizontal aligned handles, Bezier |
| Stepped | Constant interpolation |
| Plateau | Flat handles at local extremes and end keys, automatic elsewhere |

Blender stores interpolation on the *outgoing* segment of a key, so Linear / Stepped change the segment leaving
each selected key. Each button is a single undo step.

### 3. Simplify (live preview)
1. Select a run of **3+ consecutive keys** (on one or several curves) and press **Simplify Selected Keys**.
2. **Move the mouse** (Shift = fine) or drag the **Tolerance** slider in the sidebar. The real curves are
   rebuilt live, so what you see is exactly what you'll get. A bar at the bottom shows tolerance and
   `keys before → after`.
3. **Click / Enter / Apply** keeps the result (one undo step). **Esc / right-click / Cancel** restores the
   curves exactly as they were.

The first and last key of each selected run are always kept. Tolerance is a percentage of each curve's value
range over the selection, so one slider suits location, rotation and scale at once. Keys are removed least
important first, and the preview of the tolerance is checked against Blender's own curve evaluation (see Tests).

### 4. Retiming Lattice
1. Select keys on one or more curves, press **Retime Selection**.
2. Two vertical edges with grips mark the time range of the selection. **Drag an edge** to stretch or
   compress: every selected key and its handle x-lengths are scaled about the opposite edge, so spacing and
   shape are preserved. **Ctrl** snaps to whole frames.
3. **Enter / Apply** keeps it, **Esc / Cancel** puts everything back. You can drag several times before
   confirming.

*Ripple Later Keys* (default on) moves unselected keys beyond the edge by the same amount on the affected curves,
so they never collide with the retimed range. Turn it off to leave them where they are.

## Limitations (please read)

* **The drawing and mouse-driven parts have not been run inside a live Blender window.** They were written
  against the Blender 5.1 Python API, but the development environment is headless (no GUI Blender available),
  so the overlay drawing (ghost, simplify HUD, retime lattice) and the modal event handling are untested
  in real use. Expect to find rough edges there; everything underneath them is tested (below).
* The ghost compensates for degree display of rotation channels and for *Normalize*; both are
  re-implementations of what Blender does and could be slightly off in unusual cases. NLA time mapping and
  Graph Editor *seconds* display are assumed (x = frames × fps_base / fps in seconds mode) and unverified.
* Simplify plans the removal order up front: roughly 1 ms per key, so a few thousand selected keys pause for a
  few seconds when you press the button (the slider is instant afterwards).
* Ghosts are matched to curves by (action, data path, array index); two slots of one action with the same path
  would share a ghost.
* Not implemented: keyboard shortcuts (buttons only), and the Drivers editor (only tangents work there).

## Tests

Headless tests run against a real `bpy` (`pip install bpy`, Python 3.11+ depending on the bpy version):

```bash
python tests/test_addon.py            # registration/toggles, snapshots, tangents, ghost, retime, simplify
python tests/test_simplify_model.py   # simplify error model vs. Blender's real curve evaluation
```

`test_simplify_model.py` removes keys with the planned tolerance, rebuilds the curve in Blender, evaluates it and
checks the true maximum deviation stays within the tolerance, for auto / auto-clamped handles and both F-Curve
auto-smoothing modes.

## Layout

```
maya_graph_editor/
  __init__.py  core.py          registration, preferences, per-tool toggles, settings
  common.py                     curve snapshots, unit/normalisation mapping, drawing helpers
  ghost.py  tangents.py  simplify.py  retime.py      the four tools
  simplify_core.py              removal-order maths (numpy only)
  blender_manifest.toml
tests/  build.py
```
