"""Tool - Stacked Overview (experimental, read-only).

Maya's stacked view gives every curve its own lane.  Blender doesn't let
add-ons change how the Graph Editor draws or edits its curves, so a true
stacked *editing* view isn't possible (see docs/research_stacked_view.md).
What an add-on can do is draw an overview on top: each shown curve in its
own lane, scaled to fit, with its keys marked and the same time axis as
the editor underneath.  Good for reading timing across many channels at
once; toggle it off to edit.
"""

import bpy
import numpy as np

from . import common

_handle = None
MAX_LANES = 40


def lane_layout(count, height, top_margin=34, bottom_margin=30):
    """[(y_bottom, y_top), ...] for `count` lanes, first lane at the top."""
    count = min(count, MAX_LANES)
    if count <= 0:
        return []
    usable = max(height - top_margin - bottom_margin, 10)
    lane = usable / count
    top = height - top_margin
    return [(top - (i + 1) * lane + 2, top - i * lane - 2) for i in range(count)]


def lane_points(xs, ys, x_px, y_lo, y_hi):
    """Scale values into a lane; flat curves sit in the middle."""
    ys = np.asarray(ys, dtype=np.float64)
    lo, hi = float(ys.min()), float(ys.max())
    if hi - lo < 1e-9:
        py = np.full(len(ys), 0.5 * (y_lo + y_hi))
    else:
        pad = (y_hi - y_lo) * 0.12
        py = y_lo + pad + (ys - lo) / (hi - lo) * (y_hi - y_lo - 2 * pad)
    return list(zip(np.asarray(x_px).tolist(), py.tolist()))


def channel_label(fc):
    path = fc.data_path
    name = path.rsplit(".", 1)[-1]
    owner = path.rsplit(".", 1)[0] if "." in path else ""
    axis = "XYZW"[fc.array_index] if fc.array_index < 4 else str(fc.array_index)
    if name.endswith("quaternion"):
        axis = "WXYZ"[fc.array_index] if fc.array_index < 4 else axis
    bone = owner.split('"')[1] if '"' in owner else ""
    return ("%s  %s %s" % (bone, name, axis)).strip()


def _draw():
    ctx = bpy.context
    space, region, scene = ctx.space_data, ctx.region, ctx.scene
    if (space is None or space.type != 'GRAPH_EDITOR' or space.mode != 'FCURVES'
            or region is None or scene is None or not scene.mge_settings.stacked_show):
        return
    try:
        col = common.ui_colors()
        curves = common.visible_fcurves(ctx)
        w, h = region.width, region.height
        common.draw_rect(0, 0, w, h, (col["bg"][0], col["bg"][1], col["bg"][2], 0.97))
        title = "STACKED OVERVIEW (read-only, experimental)   %d curve%s" % (
            len(curves), "" if len(curves) == 1 else "s")
        if len(curves) > MAX_LANES:
            title += "   showing the first %d" % MAX_LANES
        common.draw_text(12, h - 24, title, 14, col["text"])
        common.draw_text(12, 10, "same time axis as the editor · pan / zoom as usual · "
                         "turn Stacked Overview off to edit", 11, col["dim"])
        if not curves:
            return
        ox, _oy, sx, _sy = common.view_affine(region)
        tscale = common.time_scale(space, scene)
        n_samples = max(int(w / 4), 16)
        px = np.linspace(0.0, float(w), n_samples)
        for fc, (y_lo, y_hi) in zip(curves, lane_layout(len(curves), h)):
            nscale, noff = common.nla_mapping(fc)
            frames = ((px - ox) / (sx * tscale) - noff) / nscale
            ys = [fc.evaluate(float(f)) for f in frames]
            common.draw_rect(0, y_lo, w, y_hi, common.with_alpha(col["track"], 0.25))
            rgb = tuple(fc.color)
            common.draw_polyline(lane_points(frames, ys, px, y_lo, y_hi),
                                 (rgb[0], rgb[1], rgb[2], 1.0), 1.5)
            lo, hi = min(ys), max(ys)
            for k in fc.keyframe_points:
                kx = ox + (k.co[0] * nscale + noff) * tscale * sx
                if 0 <= kx <= w:
                    f = 0.5 if hi - lo < 1e-9 else (k.co[1] - lo) / (hi - lo)
                    pad = (y_hi - y_lo) * 0.12
                    ky = y_lo + pad + min(max(f, 0.0), 1.0) * (y_hi - y_lo - 2 * pad)
                    c = col["active"] if k.select_control_point else col["text"]
                    common.draw_rect(kx - 2, ky - 2, kx + 2, ky + 2, c)
            if y_hi - y_lo >= 12:
                common.draw_text(8, y_hi - 13 * common.hud_scale(), channel_label(fc), 11, col["dim"])
    except Exception:
        common.log_exception("stacked overview")


class MGE_OT_stacked_toggle(bpy.types.Operator):
    bl_idname = "mge.stacked_toggle"
    bl_label = "Stacked Overview"
    bl_description = ("Show every curve in its own lane on top of the Graph Editor "
                      "(read-only, experimental). Click again to go back to editing")
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def execute(self, context):
        st = common.get_settings(context)
        st.stacked_show = not st.stacked_show
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_PT_stacked(bpy.types.Panel):
    bl_label = "Stacked Overview"
    bl_idname = "MGE_PT_stacked"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 16
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        st = common.get_settings(context)
        self.layout.operator("mge.stacked_toggle", icon='ALIGN_JUSTIFY', depress=st.stacked_show)
        self.layout.label(text="Read-only: turn off to edit")


classes = (MGE_OT_stacked_toggle, MGE_PT_stacked)


def register_tool():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceGraphEditor.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL')


def unregister_tool():
    global _handle
    if _handle is not None:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    common.redraw_graph_editors()
