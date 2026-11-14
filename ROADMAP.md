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

## Next: Phase 4 - Blocking and overlap (v1.3)

What animators coming from Maya reach for daily once the basics are in place.

| Item | What it does | Effort |
|---|---|---|
| **Stepped preview** | One toggle shows the selected objects' animation stepped for blocking review, without touching the keys (adds/removes a Stepped modifier on every curve). Toggle off and the splines are back. | S |
| **Round to whole frames** | Button, plus an "auto" option for Retime, Region and Time Warp, so stretching never leaves keys on sub-frames. | S |
| **Offset / stagger** | Live slider that shifts each selected curve (or bone) a little later than the previous one: quick overlap and follow-through. Order by selection, hierarchy or channel. | M |
| **Seamless loop** | For cycles: copies the first key to the end (or matches them), lines up their tangents, sets Cycle infinity. One click. | S |
| **Key sliders hub** | One panel for Blender's built-in slider tools (Ease, Push/Pull, Blend to Neighbour, Scale Average, Shear, Butterworth...), same live-preview feel and shortcuts. Cheap: they already exist, just buried. | S |
| **Equalize handle lengths** | Maya-style "non-weighted" tangents: reset handle lengths to a third of the neighbouring segments *(exists in Blender as Equalize Handles; make it one click)*. | S |

## Phase 5 - Finding and showing curves (v1.4)

| Item | What it does | Effort |
|---|---|---|
| **Channel sets** | Save the visible/selected channels as a named set ("arms", "spine rot") and switch between sets in one click. Stored in the .blend. | M |
| **Isolate curve** | Toggle to show only the selected curve(s); toggle back restores what was visible. | S |
| **Auto-frame** | Optionally frame the selection whenever it changes (Maya's auto frame), with padding. | S |
| **Select helpers** | Keys at the playhead (all curves), keys in the preview range, every Nth key, invert per curve. | S |
| **Ghost from another source** | Snapshot a curve from another action, take or object and overlay it, e.g. compare against a mocap reference. | M |
| **Partial swap** | Swap only the selected key range with the buffer curve instead of the whole curve. | S |

## Phase 6 - Generators and shapes (v1.5)

| Item | What it does | Effort |
|---|---|---|
| **Overlap generator** | Follow-through for a chain (tail, antenna, cloth bone): offset + damping down the chain, live preview, baked to keys. | L |
| **Noise / settle** | Add controllable noise or a settle (decaying wiggle) to selected keys, live preview, seed. | M |
| **Curve shape library** | Save a curve's shape (e.g. a good ease or bounce) and apply it to other keys, scaled to their time and value range. | M |
| **Copy / paste with Maya options** | Paste modes: insert, replace range, merge, scale to fit, at playhead. *(Blender has offset/merge; this adds replace and scale-to-fit.)* | M |
| **Stacked view (research)** | Maya's lanes-per-curve view. Blender doesn't let add-ons change how the editor draws curves, so this needs a prototype first (overlay drawing or a normalised offset trick) before committing. | L |

## Phase 7 - Platform and quality (ongoing)

| Item | Notes | Effort |
|---|---|---|
| Submit to extensions.blender.org | Prepared and validated; the submission is the maintainer's | S |
| "What's new" popup after an update | One short screen per version, with the GIF | S |
| More languages + runtime strings | Japanese, Chinese, French, German, Portuguese; translate key counts | M |
| Larger HUD text and a colour-blind-safe ghost palette | Preferences | S |
| CI on Blender's daily build | Catch API changes before a release breaks the add-on | S |
| Faster Simplify planning | Vectorise the planner; matters for multi-thousand-key mocap | M |
| Settings presets | Export/import tool settings and shortcuts between machines | S |

## Still open from earlier phases

| Item | Notes | Effort |
|---|---|---|
| An animator's hands-on feedback | Everything is tested, but feel is best judged by use | S |
| Verify ghosts with NLA time mapping and the *seconds* display | Assumed, not tested | S |
| Region lattice re-reads the display mapping during drags | Matters only with *Normalize* on | S |

## Suggested order

1. ~~Phases 0-3~~ (v1.1, v1.2): done.
2. Hands-on feedback on v1.2, fixes, then extensions.blender.org submission (Phase 7, first item).
3. **Phase 4** (v1.3): stepped preview, round to frames, offset/stagger, seamless loop, sliders hub. Mostly small,
   high daily value, and they reuse the existing slider and snapshot code.
4. **Phase 5** (v1.4): channel sets, isolate, auto-frame, select helpers.
5. **Phase 6** (v1.5): generators and shape library; prototype stacked view before deciding on it.
