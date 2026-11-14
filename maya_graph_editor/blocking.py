"""Tool - Blocking helpers.

Stepped Preview
    Shows the animation stepped (held poses) for blocking review.  It sets
    every key to Constant interpolation and remembers what each key had, on
    the action itself, so toggling it off (even after saving and reopening)
    puts the splines back.  Keys added while the preview is on get Blender's
    default interpolation when it is turned off.
Round to Whole Frames
    Moves the selected keys (and their handles) to the nearest whole frame;
    keys that land on the same frame are merged.  "Auto" does this after
    Retime / Region, Time Warp and Stagger.
Seamless Loop
    Makes the last key match the first and turns on Cycle infinity, so the
    curve loops without a pop.
Equalize Handles
    Maya's non-weighted tangents: handle lengths become a third of the
    neighbouring segment, keeping each tangent's angle.
"""

import json

import bpy

from . import common, curves

PROP = "mge_stepped"


def _curve_id(fc):
    return "%d|%s" % (fc.array_index, fc.data_path)


def _target_curves(context):
    """Curves of the selected objects (shown or not); falls back to visible curves."""
    from .retime import rig_fcurves
    out = rig_fcurves(context)
    return out or common.editable_fcurves(context)


# --------------------------------------------------------------------------
# Stepped preview
# --------------------------------------------------------------------------

def stepped_active(fcurves):
    return any(fc.id_data is not None and PROP in fc.id_data for fc in fcurves)


def stepped_on(fcurves):
    by_action = {}
    for fc in fcurves:
        action = fc.id_data
        if action is None or action.library is not None:
            continue
        store = by_action.setdefault(action.name_full, (action, json.loads(action.get(PROP, "{}"))))[1]
        cid = _curve_id(fc)
        if cid in store:
            continue  # already stepped: keep the original record
        store[cid] = {"%.4f" % k.co[0]: k.interpolation for k in fc.keyframe_points}
        for k in fc.keyframe_points:
            k.interpolation = 'CONSTANT'
        fc.update()
    for action, store in by_action.values():
        action[PROP] = json.dumps(store)
    return len(by_action)


def stepped_off(fcurves):
    default = bpy.context.preferences.edit.keyframe_new_interpolation_type
    actions = {}
    for fc in fcurves:
        action = fc.id_data
        if action is None or PROP not in action:
            continue
        store = actions.setdefault(action.name_full, (action, json.loads(action[PROP])))[1]
        saved = store.pop(_curve_id(fc), None)
        if saved is None:
            continue
        for k in fc.keyframe_points:
            k.interpolation = saved.get("%.4f" % k.co[0], default)
        fc.update()
    for action, store in actions.values():
        if store:
            action[PROP] = json.dumps(store)
        else:
            del action[PROP]
    return len(actions)


# --------------------------------------------------------------------------
# Round to whole frames
# --------------------------------------------------------------------------

def round_keys(fc, only_selected=True):
    """Returns the number of keys moved."""
    moved = 0
    for k in fc.keyframe_points:
        if only_selected and not k.select_control_point:
            continue
        x = k.co[0]
        dx = round(x) - x
        if abs(dx) < 1e-6:
            continue
        k.co = (x + dx, k.co[1])
        k.handle_left = (k.handle_left[0] + dx, k.handle_left[1])
        k.handle_right = (k.handle_right[0] + dx, k.handle_right[1])
        moved += 1
    if moved:
        fc.update()
        fc.keyframe_points.deduplicate()
        fc.update()
    return moved


def auto_round(context, fcurves):
    """Called by the retiming tools after Apply when 'Auto' is on."""
    try:
        if common.tool_enabled("blocking") and common.get_settings(context).round_auto:
            for fc in fcurves:
                round_keys(fc)
    except Exception:
        common.log_exception("auto round")


# --------------------------------------------------------------------------
# Seamless loop / equalize handles
# --------------------------------------------------------------------------

def seamless_loop(fc):
    """Last key takes the first key's value; Cycle infinity on both sides."""
    kps = fc.keyframe_points
    if len(kps) < 2:
        return False
    first, last = kps[0], kps[len(kps) - 1]
    dy = first.co[1] - last.co[1]
    last.co = (last.co[0], first.co[1])
    last.handle_left = (last.handle_left[0], last.handle_left[1] + dy)
    last.handle_right = (last.handle_right[0], last.handle_right[1] + dy)
    auto = {'AUTO', 'AUTO_CLAMPED'}
    if not ({first.handle_left_type, first.handle_right_type,
             last.handle_left_type, last.handle_right_type} <= auto):
        # manual tangents: give both ends the same slope (average of what they had)
        def slope(k, side):
            h = k.handle_right if side == 'R' else k.handle_left
            dx = h[0] - k.co[0]
            return (h[1] - k.co[1]) / dx if abs(dx) > 1e-9 else 0.0
        s = 0.5 * (slope(first, 'R') + slope(last, 'L'))
        for k in (first, last):
            for name in ("handle_left", "handle_right"):
                h = getattr(k, name)
                setattr(k, name, (h[0], k.co[1] + s * (h[0] - k.co[0])))
    curves.set_infinity(fc, 'BOTH', 'CYCLE')  # auto handles become cycle-aware
    fc.update()
    return True


def equalize_handles(fc):
    """Selected keys: handle length = 1/3 of the neighbouring segment, angle kept."""
    kps = fc.keyframe_points
    n = len(kps)
    count = 0
    for i, k in enumerate(kps):
        if not (k.select_control_point or k.select_left_handle or k.select_right_handle):
            continue
        x, y = k.co
        left = (x - kps[i - 1].co[0]) / 3.0 if i > 0 else None
        right = (kps[i + 1].co[0] - x) / 3.0 if i < n - 1 else None
        left = right if left is None else left
        right = left if right is None else right
        if left is None:
            continue
        for name, length, sign in (("handle_left", left, -1.0), ("handle_right", right, 1.0)):
            h = getattr(k, name)
            dx = h[0] - x
            s = (h[1] - y) / dx if abs(dx) > 1e-9 else 0.0
            setattr(k, name, (x + sign * length, y + s * sign * length))
        count += 1
    if count:
        fc.update()
    return count


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class _Op:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None


class MGE_OT_stepped_preview(_Op, bpy.types.Operator):
    bl_idname = "mge.stepped_preview"
    bl_label = "Stepped Preview"
    bl_description = ("Show the selected objects' animation stepped for blocking review; "
                      "click again to get the original interpolation back")

    def execute(self, context):
        targets = _target_curves(context)
        if not targets:
            self.report({'WARNING'}, "Select an animated object first")
            return {'CANCELLED'}
        if stepped_active(targets):
            stepped_off(targets)
            self.report({'INFO'}, "Stepped preview off: interpolation restored")
        else:
            stepped_on(targets)
            self.report({'INFO'}, "Stepped preview on (%d curves)" % len(targets))
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_round_keys(_Op, bpy.types.Operator):
    bl_idname = "mge.round_keys"
    bl_label = "Round to Whole Frames"
    bl_description = "Move the selected keys to the nearest whole frame"

    def execute(self, context):
        moved = sum(round_keys(fc) for fc in common.editable_fcurves(context))
        self.report({'INFO'}, "%d key(s) moved to whole frames" % moved)
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_seamless_loop(_Op, bpy.types.Operator):
    bl_idname = "mge.seamless_loop"
    bl_label = "Seamless Loop"
    bl_description = ("Make the last key of the selected curves match the first and turn on "
                      "Cycle infinity, so the animation loops without a pop")

    def execute(self, context):
        n = sum(seamless_loop(fc) for fc in curves.target_fcurves(context))
        if not n:
            self.report({'WARNING'}, "Select curves with at least two keys")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_equalize_handles(_Op, bpy.types.Operator):
    bl_idname = "mge.equalize_handles"
    bl_label = "Equalize Handles"
    bl_description = ("Reset the handle lengths of the selected keys to a third of the "
                      "neighbouring segment, keeping their angle (Maya non-weighted tangents)")

    def execute(self, context):
        n = sum(equalize_handles(fc) for fc in common.editable_fcurves(context))
        if not n:
            self.report({'WARNING'}, "No keyframes selected")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_PT_blocking(bpy.types.Panel):
    bl_label = "Blocking"
    bl_idname = "MGE_PT_blocking"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 10

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        on = stepped_active(_target_curves(context))
        row = layout.row()
        row.scale_y = 1.3
        row.operator("mge.stepped_preview", icon='IPO_CONSTANT', depress=on)
        row = layout.row(align=True)
        row.operator("mge.round_keys", icon='SNAP_INCREMENT')
        row.prop(st, "round_auto", text="Auto", toggle=True)
        row = layout.row(align=True)
        row.operator("mge.seamless_loop", icon='FILE_REFRESH')
        row.operator("mge.equalize_handles", icon='HANDLE_ALIGNED')


classes = (MGE_OT_stepped_preview, MGE_OT_round_keys, MGE_OT_seamless_loop,
           MGE_OT_equalize_handles, MGE_PT_blocking)


def register_tool():
    pass


def unregister_tool():
    pass
