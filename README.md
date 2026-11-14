# Maya Graph Editor Tools for Blender

Maya-style comforts for Blender's **Graph Editor**, in one add-on. Everything lives in the Graph Editor
sidebar (**N → Maya** tab). No new windows, no node graph, nothing that touches rendering or export.

| Tool | What it does |
|---|---|
| **Key Stats** | Frame and value fields for the whole selection, absolute or relative (Maya's stats boxes). |
| **Tangents** | Spline · Linear · Flat · Stepped · Plateau · Clamped, one click each, for both sides, In only or Out only. Break / Unify. Default tangent for new keys. Pie menu. |
| **Buffer / Ghost Curve** | Snapshot curves into slots A/B/C and see them as faint overlays while you edit. Swap like Maya's buffer curve. Saved in the .blend. |
| **Simplify (live preview)** | Move the mouse or drag a slider to see the curve lose keys in real time. Confirm or cancel. |
| **Retiming Lattice** | Drag an edge of a lattice around the selected keys (across curves), or type a %, to stretch or compress them in time. |
| **Curves** | One-click Pre/Post Infinity (Constant, Linear, Cycle, Cycle with Offset, Oscillate) and Euler filter. |

Each tool can be switched off independently (**Preferences → Add-ons → Maya Graph Editor Tools**, or the
collapsed *Enabled Tools* panel at the bottom of the Maya tab). A disabled tool is fully unregistered: no
operators, panel, draw handler or shortcuts.

## Install

Requires **Blender 4.2 or newer** (tested on 4.2 LTS and 5.1).

```bash
python3 build.py     # writes dist/maya_graph_editor-1.1.0.zip (+ a -legacy.zip)
```

* **Blender 4.2+:** Preferences → Get Extensions → ⌄ menu → *Install from Disk…* → pick
  `maya_graph_editor-1.1.0.zip`.
* Legacy add-on install (Preferences → Add-ons → Install from Disk) → use the `-legacy.zip`.

## Shortcuts (Graph Editor)

| Shortcut | Action |
|---|---|
| **Alt+V** | Tangent pie menu |
| **Ctrl+Alt+B** | Ghost: snapshot into the active slot |
| **Ctrl+Alt+Shift+B** | Ghost: swap with the active slot |
| **Ctrl+Alt+X** | Simplify selected keys |
| **Ctrl+Alt+T** | Retime selection |

They are listed and rebindable in the add-on preferences. The GUI test checks that none of them clashes with
Blender's default Graph Editor keymap.

## Using the tools

### Key Stats
* **Absolute:** *Frame* shows the first selected frame; typing a frame moves the whole selection there (spacing
  kept). *Value* shows the shared value (the average if they differ); typing sets every selected key to it.
* **Relative:** both fields start at 0 for a new selection; typing or dragging offsets every selected key.
* Rotation is shown in degrees when every selected key is on a rotation curve. Handles move with their keys.

### Tangents (applied to selected keyframes)

| Button | Blender equivalent |
|---|---|
| Spline | Automatic handles, Bezier (can overshoot, like Maya spline) |
| Clamped | Auto-clamped handles, Bezier (no overshoot) |
| Linear | Linear interpolation |
| Flat | Horizontal handles, Bezier |
| Stepped | Constant interpolation |
| Plateau | Flat handles at local extremes and end keys, automatic elsewhere |

* **Both / In / Out** above the buttons chooses which tangent changes. **Ctrl+click** a button = In only,
  **Alt+click** = Out only. In Blender, interpolation belongs to the segment *leaving* a key, so *In* Linear or
  Stepped changes the previous key's segment, which is the one entering the selected key. One-sided changes
  break the handles so the other side keeps its shape.
* **Break** frees the in/out handles; **Unify** lines them up again (average direction, each keeps its length).
* **New Keys** sets Blender's own preference for newly inserted keys (Spline, Clamped, Linear, Stepped).
* Optional: the six buttons as icons in the Graph Editor header (add-on preferences).

### Buffer / Ghost Curve
* Pick slot **A, B or C**, then **Snapshot** (selected curves, or all visible ones if none is selected).
  Each slot has its own colour and eye toggle, so you can compare up to three versions at once.
* Ghosts are only drawn on top of the Graph Editor: they can't be selected or get in the way of editing.
* **Swap** (Maya's "swap buffer curve"): the curve takes the slot's shape and its current shape goes into the slot.
* **Clear** empties the active slot, **Clear All** every slot.
* **Range:** the curve's key range, or the scene/preview frame range (shows cycles and extrapolation).
* **Solid** or **Dashed** lines, adjustable width.
* **Save Ghosts in File** (on by default) keeps them in the .blend, stored on each action when you save.

### Simplify (live preview)
1. Select a run of **3+ consecutive keys** (on one or several curves) and press **Simplify Selected Keys**.
2. **Move the mouse** (Shift = fine) or drag the **Tolerance** slider in the sidebar. The real curves are
   rebuilt live, so what you see is exactly what you'll get. A bar at the bottom shows tolerance and
   `keys before → after`.
3. **Click / Enter / Apply** keeps the result (one undo step). **Esc / right-click / Cancel** restores the
   curves exactly as they were.

The first and last key of each selected run are always kept. Tolerance is a percentage of each curve's value
range over the selection, so one slider suits location, rotation and scale at once. Big selections (300+ keys)
are analysed in the background with a progress bar; Esc during analysis changes nothing.

### Retiming Lattice
1. Select keys on one or more curves, press **Retime Selection**.
2. **Drag an edge** to stretch or compress: selected keys and their handle x-lengths scale about the opposite
   edge, so spacing and shape are preserved. **Ctrl** snaps to whole frames. Or **type a percentage**
   (e.g. `5` `0` for 50%) and press Enter.
3. **Enter / Apply** keeps it, **Esc / Cancel** puts everything back. You can drag several times before confirming.

Without opening the lattice: set **Scale %** and an anchor (**Start / Center / End**) in the panel and press ✓.
*Ripple Later Keys* (default on) moves unselected keys beyond the edge along with it on the affected curves.

### Curves
* **Pre / Post Infinity** rows set how each end of the selected curves continues; the active curve's current mode
  is highlighted. Cycle modes use a Cycles modifier. Blender has one Constant/Linear setting for both ends, so
  choosing Constant or Linear for one end also changes a non-cycling other end (the add-on tells you).
* **Euler Filter** runs Blender's discontinuity filter on the selected rotation curves.

## Updating from GitHub

**Preferences → Add-ons (or Extensions) → Maya Graph Editor Tools → Updates**:

* **Check for Updates** asks GitHub for the latest release of this repository and compares versions.
* **Install x.y.z** downloads the right zip (Extension or legacy), checks its SHA-256 when GitHub provides one,
  and installs it with Blender's own installer. **Release Notes** opens the release page.
* **Check for updates on startup** (off by default) checks at most once a day.
* Needs Blender's **Allow Online Access** (Preferences → System → Network). Nothing is downloaded otherwise.

### Publishing a release (maintainer)
1. Bump the version in **both** `maya_graph_editor/blender_manifest.toml` and `bl_info` in `__init__.py`
   (`build.py` refuses to build if they differ).
2. Commit, then tag and push: `git tag v1.1.0 && git push origin v1.1.0`.
3. The **Release** GitHub Action builds both zips and publishes the release. That's what the updater installs.

## Tests

Every push runs **Tests** on GitHub Actions:

* **Headless** (`pip install bpy`): data logic of every tool against real F-Curves.
  ```bash
  python tests/test_addon.py            # registration/toggles, snapshots, tangents, ghost, retime, simplify
  python tests/test_v11.py              # v1.1 features: sides, break/unify, infinity, stats, slots, saving
  python tests/test_simplify_model.py   # simplify error model vs. Blender's real curve evaluation
  python tests/test_updater.py          # updater: versions, asset choice, checksum, Blender installer
  ```
* **GUI** in real Blender **4.2 LTS and 5.1** under Xvfb (`tests/gui/run_gui_tests.py`), driven by simulated
  mouse and keyboard events. It checks the ghost draws (solid and dashed) and that the overlay mapping matches
  Blender's view within 1 px. It drives simplify (mouse drag preview, Esc restore, Enter keep, one-step undo,
  background analysis) and retime (edge hover, drag, ripple, typed %). It also checks shortcut conflicts, and
  fails on any Python traceback.

## Limitations

* CI proves the overlays draw at the right place and the interactions work, but its screenshots come out blank
  under the virtual display, so **how the overlays look** (colours, readability) has only been designed, not
  inspected. Feedback welcome.
* The ghost compensates for degree display of rotation channels and for *Normalize* by re-implementing what
  Blender does; unusual setups could be slightly off. NLA time mapping and *seconds* display are not verified.
* Ghosts are matched to curves by (action, data path, array index); renaming an action loses its ghosts, and two
  slots of one action with the same path would share a ghost.
* Only Tangents work in the Drivers editor.

## Layout

```
maya_graph_editor/
  __init__.py  core.py          registration, preferences, per-tool toggles, settings
  common.py                     curve snapshots, unit/normalisation mapping, drawing helpers
  ghost.py  tangents.py  simplify.py  retime.py  curves.py  stats.py      the tools
  keymaps.py                    rebindable shortcuts
  updater.py                    GitHub release check / install
  simplify_core.py              removal-order maths (numpy only)
  blender_manifest.toml
tests/  tests/gui/  build.py  .github/workflows/
```
