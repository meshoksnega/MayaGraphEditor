"""Tool - Mocap cleanup in one click.

For every curve with 3+ selected keys:
  1. Bake (optional): resample the selected time range to a key on every
     whole frame.  Modifiers are muted while sampling, so a Noise modifier
     isn't baked in on top of itself.
  2. Simplify to the tolerance (same algorithm and units as Simplify).
  3. Apply a tangent type to what's left.
Everything is one undo step.
"""

import math

import bpy
import numpy as np

from . import common, simplify, simplify_core, tangents


def bake_selection(fc):
    """Replace the selected time range with one selected key per whole frame.
    Returns the number of keys baked (0 if fewer than 2 keys selected)."""
    kps = fc.keyframe_points
    sel_x = [k.co[0] for k in kps if k.select_control_point]
    if len(sel_x) < 2:
        return 0
    x0, x1 = min(sel_x), max(sel_x)
    muted = [m.mute for m in fc.modifiers]
    for m in fc.modifiers:
        m.mute = True
    try:
        frames = sorted({x0, x1} | set(range(math.ceil(x0), math.floor(x1) + 1)))
        values = [fc.evaluate(float(f)) for f in frames]
    finally:
        for m, was in zip(fc.modifiers, muted):
            m.mute = was
    for k in [k for k in kps if x0 - 1e-6 <= k.co[0] <= x1 + 1e-6][::-1]:
        kps.remove(k, fast=True)
    for k in kps:
        k.select_control_point = k.select_left_handle = k.select_right_handle = False
    for f, v in zip(frames, values):
        k = kps.insert(float(f), v, options={'FAST'})
        k.interpolation = 'BEZIER'
        k.handle_left_type = k.handle_right_type = 'AUTO_CLAMPED'
        k.select_control_point = k.select_left_handle = k.select_right_handle = True
    fc.update()
    return len(frames)


def simplify_selection(fc, pct):
    """Simplify the selected keys of fc to `pct` tolerance; returns keys removed."""
    plan = simplify.build_curve_plan(fc)
    if plan is None:
        return 0
    cnt = simplify_core.removal_count(plan.cum, plan.span * pct / 100.0)
    if cnt:
        keep = np.setdiff1d(np.arange(plan.snap.n), plan.order[:cnt])
        plan.snap.write(fc, keep=keep)
    return cnt


def cleanup_curve(fc, bake, pct, tangent):
    """Returns (keys before, keys after)."""
    before = len(fc.keyframe_points)
    if bake:
        bake_selection(fc)
    simplify_selection(fc, pct)
    if tangent != 'KEEP':
        tangents.apply_tangent(fc, tangent, 'BOTH')
    return before, len(fc.keyframe_points)


class MGE_OT_cleanup(bpy.types.Operator):
    bl_idname = "mge.cleanup"
    bl_label = "Clean Up Selected Keys"
    bl_description = ("Bake the selected range to every frame, simplify it to the tolerance "
                      "and set tangents, in one step")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None

    def execute(self, context):
        st = common.get_settings(context)
        curves = [fc for fc in common.editable_fcurves(context)
                  if sum(k.select_control_point for k in fc.keyframe_points) >= 2]
        if not curves:
            self.report({'WARNING'}, "Select keys on at least one curve")
            return {'CANCELLED'}
        wm = context.window_manager
        wm.progress_begin(0, len(curves))
        total_before = total_after = 0
        try:
            for i, fc in enumerate(curves):
                b, a = cleanup_curve(fc, st.cleanup_bake, st.cleanup_tolerance, st.cleanup_tangent)
                total_before += b
                total_after += a
                wm.progress_update(i + 1)
        finally:
            wm.progress_end()
        self.report({'INFO'}, "Cleaned %d curve(s): %d -> %d keys"
                    % (len(curves), total_before, total_after))
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_PT_cleanup(bpy.types.Panel):
    bl_label = "Mocap Cleanup"
    bl_idname = "MGE_PT_cleanup"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 8
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        col = layout.column()
        col.prop(st, "cleanup_bake")
        col.prop(st, "cleanup_tolerance", slider=True)
        col.prop(st, "cleanup_tangent")
        row = layout.row()
        row.scale_y = 1.3
        row.operator("mge.cleanup", icon='BRUSH_DATA')


TANGENT_ITEMS = [('KEEP', "Keep", "Leave tangents as they are")] + \
    [(i, l, d) for i, l, d, _icon in tangents.TANGENT_TYPES]

classes = (MGE_OT_cleanup, MGE_PT_cleanup)


def register_tool():
    pass


def unregister_tool():
    pass
