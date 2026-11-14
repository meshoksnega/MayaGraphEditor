# Listing text for extensions.blender.org

Copy each block into the matching field of the submission form.

## Name
Maya Graph Editor Tools

## Tagline (63 characters, the limit is 64)
Maya-style Graph Editor tools: tangents, buffer curve, retiming

## Tags
Animation

## Description

```markdown
**The Graph Editor comforts Maya animators miss, inside Blender's own Graph Editor.**
Everything lives in the sidebar (**N → Maya** tab). No new windows, nothing that touches rendering or export,
and every tool can be switched off on its own.

### Tools

- **Buffer curve.** Snapshot curves into three slots and see them as faint overlays while you edit.
  **Swap** to A/B two versions. Saved with the .blend.
- **One-click tangents.** Spline, Linear, Flat, Stepped, Plateau and Clamped, for both sides, in only or out only,
  plus Break / Unify and the default tangent for new keys. Pie menu on **Alt+V**.
- **Simplify with live preview.** Drag the mouse and watch the curve lose keys in real time; nothing is removed
  until you confirm. The tolerance is checked against Blender's own curve evaluation.
- **Retime / Region lattice.** A box around the selected keys, across curves. Edges stretch time or scale values,
  corners do both, inside moves. Type a %, fit to the preview range or markers, or retime the whole rig.
- **Tween.** Slide selected keys between their neighbours, with overshoot (like Tween Machine).
- **Smooth.** Remove jitter with a blur slider; steady motion stays straight.
- **Time Warp.** Ease the timing inside a range (slow in / slow out) without changing values.
- **Mocap cleanup.** Bake, simplify and set tangents in one click.
- **Curves.** One-click Pre/Post Infinity (Constant, Linear, Cycle, Cycle with Offset, Oscillate) and Euler filter.
- **Key stats.** Frame and value fields for the whole selection, absolute or relative, in degrees for rotation.

Every interactive tool previews on the real curves: **Enter** keeps the result as one undo step,
**Esc** puts everything back exactly.

### Getting started

1. Open a Graph Editor and press **N** for the sidebar, then the **Maya** tab.
2. Select some keys and click a tangent button, or press **Ctrl+Alt+X** (Simplify),
   **Ctrl+Alt+T** (Retime / Region) or **Ctrl+Alt+B** (buffer curve snapshot).
3. Shortcuts can be changed in the add-on preferences.

### Good to know

- Works in Blender 4.2 LTS and newer; tested automatically in 4.2 and 5.1, including the on-screen tools.
- Interface available in English, Russian and Spanish.
- Source, documentation and issue tracker: https://github.com/meshoksnega/MayaGraphEditor
```

## Support / issue tracker URL
https://github.com/meshoksnega/MayaGraphEditor/issues

## Website
https://github.com/meshoksnega/MayaGraphEditor

## Suggested images (in `docs/media/`)
- Featured image: `ghost.jpg` (buffer curve)
- Gallery: `demo_region.gif`, `simplify.jpg`, `demo_tween.gif`, `demo_smooth.gif`, `demo_warp.gif`, `russian.jpg`

## Before submitting

The add-on includes a GitHub updater and declares the `network` permission for it. It already switches itself
off when installed from extensions.blender.org, but the platform's rules don't allow add-ons to update
themselves, so a reviewer may still ask for it to be removed. The safe route is to submit a build without
`updater.py` and without the `[permissions] network` line.
