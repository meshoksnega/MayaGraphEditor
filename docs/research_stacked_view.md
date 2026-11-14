# Research: a Maya-style stacked view in Blender

**Question.** Maya's Graph Editor can show each curve in its own lane ("stacked view") and still edit it there.
Can an add-on give Blender the same?

**Answer.** Not as an editing view. An overlay overview is possible, and that is what ships as the experimental
*Stacked Overview* tool.

## What was looked at

| Approach | Result |
|---|---|
| Change how the Graph Editor draws its curves | Not possible. The editor's curve drawing and key picking are built into Blender; add-ons can only draw *on top* (draw handlers), not replace or move what Blender draws. |
| Use *Normalize* and offset each curve | Normalize scales every curve to -1..1 but always around the same centre. There is no per-curve display offset an add-on can set. |
| Temporarily offset the real key values per curve | Would work visually, but it changes the animation while the view is on. A crash, a save, or a render in that state would bake the offsets in. Rejected as unsafe. |
| An F-Curve modifier per curve that adds an offset | Same problem (it changes evaluated values, so the character moves), and handles and keys are still drawn at their real values, so the curve and its keys would separate. |
| Draw an overlay with one lane per curve | Works. Read-only: clicks still go to the real curves underneath, which are in different places, so editing through the overlay isn't possible. |

## What ships

*Stacked Overview* (off by default in use, toggle in the Maya tab): an opaque overlay with one lane per shown
curve, each scaled to fit its lane, keys marked (selected keys highlighted), channel names, and the same time axis
as the editor underneath, so panning and zooming in time still work. It is for reading timing across many
channels at a glance. Turn it off to edit.

## What a real stacked view would need

A change in Blender itself: a per-channel display offset/scale in the Graph Editor (like Normalize, but with an
offset per curve) that drawing, picking and transform all respect. That is a proposal for Blender's developers,
not something an add-on can add.
