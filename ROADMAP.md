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

## 1.3.1: extensions.blender.org review fixes

* **Auto Frame removed.** It re-framed the view on a timer; framing is the animator's call.
* **No dynamic (un)registration.** Every tool registers once when the add-on is enabled. Switching a tool off
  hides its panel and makes its operators, shortcuts and overlays do nothing (checked in `poll()`), with no timer.
* **No background timers.** Ghosts saved in a file are read on first use instead of by a deferred timer; What's
  New is a note in the Maya tab instead of a timed popup; the GitHub update check runs only when clicked.
  The store build (`build.py --store`) contains no timer at all; Simplify's analysis uses a modal timer that
  exists only while that operator runs.

## Done in 1.3.0 (Phases 4 to 7)

* **Blocking and overlap:** Stepped Preview, Round to Whole Frames (with Auto), Seamless Loop, Equalize Handles,
  Stagger, a Key Sliders hub for Blender's slider tools.
* **Finding and showing curves:** channel sets, Isolate, selection helpers, ghosts from another
  action, Swap Range.
* **Generators and shapes:** Overlap generator, Noise, Settle, shape library, copy/paste with Merge / Replace /
  Insert / Fit. Stacked view was researched (`docs/research_stacked_view.md`): a true stacked editing view needs
  a change in Blender, so a read-only Stacked Overview ships as experimental.
* **Platform:** `build.py --store` for extensions.blender.org, What's New popup, five more languages and
  translated counts, on-screen text size, colour-blind-safe ghost palette, weekly CI on Blender's daily build,
  Simplify planning about 4x faster, settings export/import.
* **Open items closed:** key positions are now checked against Blender itself for degrees, Normalize, NLA strips
  and the seconds display. That check found the seconds-display assumption was wrong (keys stay at frame
  positions) and it was removed. The region box follows the display under Normalize.

## Still open

| Item | Notes | Effort |
|---|---|---|
| Submit to extensions.blender.org | Build with `python build.py --store`; text in `docs/extensions_listing.md`. The submission is the maintainer's | S |
| An animator's hands-on feedback | Everything is tested, but feel is best judged by use | S |
| Native-speaker review of the translations | All seven languages | S |
| Per-curve NLA mapping in the region lattice and Stacked Overview | Ghosts already do it | M |
| True stacked editing view | Needs a per-channel display offset in Blender itself; worth proposing upstream | L |

## Ideas for later

| Item | What it does | Effort |
|---|---|---|
| Pose-to-pose breakdown across the whole rig | Tween every channel of the selected bones at the playhead, from the 3D viewport too | M |
| Motion trail hooks | Show the selected key range as a path in the viewport while editing curves | L |
| Audio waveform lane in Stacked Overview | Timing against dialogue | M |
| Per-tool tutorials | Short in-app "show me" steps for each tool | M |

## Suggested order

1. ~~Phases 0-7~~ (v1.1 to v1.3): done.
2. Hands-on feedback, then the extensions.blender.org submission.
