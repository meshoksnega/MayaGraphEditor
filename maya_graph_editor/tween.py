"""Tool - Tween / Breakdown slider (Maya's Tween Machine).

Selected keys move to an in-between of the unselected keys on either side
of their run: 0% = previous key's value, 100% = next key's value, 50% =
halfway.  -50%..150% overshoots.  Handles travel with their keys.

"Key at Playhead" inserts (or updates) a key at the current frame on the
selected curves, at the same in-between of the keys around the playhead.
"""

import bisect

import bpy
import numpy as np

from . import common, slider


def neighbour_values(y, sel):
    """For each selected key: (previous unselected value, next unselected value)."""
    n = len(y)
    prev_v = [None] * n
    nxt_v = [None] * n
    last = None
    for i in range(n):
        if not sel[i]:
            last = y[i]
        else:
            prev_v[i] = last
    last = None
    for i in range(n - 1, -1, -1):
        if not sel[i]:
            last = y[i]
        else:
            nxt_v[i] = last
    return prev_v, nxt_v


def tween_values(y, sel, bias):
    """New values for the keys (unselected ones unchanged)."""
    prev_v, nxt_v = neighbour_values(y, sel)
    out = np.array(y, dtype=np.float64)
    f = bias / 100.0
    for i in range(len(y)):
        if not sel[i]:
            continue
        a, b = prev_v[i], nxt_v[i]
        if a is None and b is None:
            continue
        if a is None:
            a = b
        if b is None:
            b = a
        out[i] = a + (b - a) * f
    return out


def shifted(snap, new_y):
    """co/hl/hr with each key moved to new_y, handles following."""
    dy = new_y - snap.co[:, 1]
    co, hl, hr = snap.co.copy(), snap.hl.copy(), snap.hr.copy()
    co[:, 1] = new_y
    hl[:, 1] += dy
    hr[:, 1] += dy
    return co, hl, hr


class TweenTool(slider.SliderTool):
    id = "tween"
    label = "TWEEN"
    op_label = "Tween Selected Keys"
    description = ("Move the selected keys to an in-between of the keys around them, "
                   "with a live preview (Maya's Tween Machine)")
    setting = "tween_bias"
    vmin, vmax = -50.0, 150.0
    snap_step = 25.0
    marks = (0.0, 50.0, 100.0)

    def prepare(self, context):
        jobs = slider.selected_jobs(context)
        jobs = [j for j in jobs if (~j.snap.selected).any()]
        return jobs or "Select keys that have unselected keys on at least one side"

    def compute(self, job, value):
        new_y = tween_values(job.snap.co[:, 1], job.snap.selected, value)
        return shifted(job.snap, new_y)

    def describe(self, value):
        if abs(value - 50.0) < 0.5:
            side = "halfway"
        elif value < 0 or value > 100:
            side = "overshoot"
        else:
            side = "towards previous" if value < 50 else "towards next"
        return "%.0f%%  (%s)" % (value, side)


TOOL = TweenTool()


def key_at_frame(fc, frame, bias):
    """Insert/update a key at `frame` between the keys around it. Returns True if keyed."""
    xs = [k.co[0] for k in fc.keyframe_points]
    if not xs:
        return False
    i = bisect.bisect_left(xs, frame)
    if i < len(xs) and abs(xs[i] - frame) < 1e-4:
        prev_i, next_i = i - 1, i + 1
    else:
        prev_i, next_i = i - 1, i
    kps = fc.keyframe_points
    a = kps[prev_i].co[1] if prev_i >= 0 else None
    b = kps[next_i].co[1] if next_i < len(kps) else None
    if a is None and b is None:
        return False
    a = b if a is None else a
    b = a if b is None else b
    fc.keyframe_points.insert(frame, a + (b - a) * bias / 100.0)
    fc.update()
    return True


class MGE_OT_tween_key(bpy.types.Operator):
    bl_idname = "mge.tween_key"
    bl_label = "Key at Playhead"
    bl_description = ("Key the selected curves at the current frame, at the Tween value "
                      "between the keys around it")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None

    def execute(self, context):
        from .curves import target_fcurves
        curves = target_fcurves(context)
        if not curves:
            self.report({'WARNING'}, "Select curves or keyframes first")
            return {'CANCELLED'}
        frame = float(context.scene.frame_current)
        bias = common.get_settings(context).tween_bias
        n = sum(key_at_frame(fc, frame, bias) for fc in curves)
        if not n:
            self.report({'WARNING'}, "No keys to tween between")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_PT_tween(bpy.types.Panel):
    bl_label = "Tween"
    bl_idname = "MGE_PT_tween"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 5

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        slider.draw_panel(layout, context, TOOL, 'IPO_EASE_IN_OUT')
        row = layout.row(align=True)
        st = common.get_settings(context)
        for v in (0, 25, 50, 75, 100):
            op = row.operator("mge.set_tween_bias", text="%d" % v,
                              depress=abs(st.tween_bias - v) < 0.01)
            op.value = v
        layout.operator("mge.tween_key", icon='KEYFRAME_HLT')


class MGE_OT_set_tween_bias(bpy.types.Operator):
    bl_idname = "mge.set_tween_bias"
    bl_label = "Tween Preset"
    bl_description = "Set the Tween value"
    bl_options = {'INTERNAL'}

    value: bpy.props.FloatProperty()

    def execute(self, context):
        common.get_settings(context).tween_bias = self.value
        return {'FINISHED'}


classes = (slider.make_operator(TOOL), MGE_OT_tween_key, MGE_OT_set_tween_bias, MGE_PT_tween)


def register_tool():
    pass


def unregister_tool():
    slider.unregister_tool_session(TOOL.id)
