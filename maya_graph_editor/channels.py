"""Tool - Channels & selection.

Channel Sets
    Save which channels are shown as a named set ("arms", "spine rot") and
    bring it back with one click.  A set stores property paths, not objects,
    so the same set works on any character with the same rig.  Sets are
    saved in the .blend.
Isolate
    Show only the selected curves; click again to restore what was visible.
Auto Frame
    Frame the selected keys whenever the selection changes (Maya's auto frame).
Select helpers
    Keys at the playhead, keys in the preview range, every Nth selected key,
    invert per curve.

Hiding uses the Graph Editor's own per-curve visibility (the eye in the
channel list), so everything can also be undone by hand there.
"""

import json

import bpy
import numpy as np

from . import common

_isolate_state = {}      # curve key -> hide flag before isolating
_frame_signature = {}    # area pointer -> last selection signature
AUTO_FRAME_INTERVAL = 0.4


def object_fcurves(context):
    """Every F-Curve of the selected objects' actions, hidden ones included."""
    objs = list(getattr(context, "selected_objects", None) or [])
    active = getattr(context, "active_object", None)
    if active is not None and active not in objs:
        objs.append(active)
    out, seen = [], set()
    for obj in objs:
        ad = obj.animation_data
        if ad is None or ad.action is None:
            continue
        for fc in common.action_fcurves(ad.action, getattr(ad, "action_slot", None)):
            key = common.curve_key(fc)
            if key not in seen:
                seen.add(key)
                out.append(fc)
    return out


def _is_picked(fc):
    return fc.select or any(k.select_control_point for k in fc.keyframe_points)


# --------------------------------------------------------------------------
# Channel sets
# --------------------------------------------------------------------------

def set_from_curves(fcurves):
    return sorted({(fc.data_path, fc.array_index) for fc in fcurves})


def apply_set(fcurves, members):
    """Show exactly the member channels. Returns how many were shown."""
    members = {tuple(m) for m in members}
    shown = 0
    for fc in fcurves:
        on = (fc.data_path, fc.array_index) in members
        fc.hide = not on
        fc.select = on
        shown += on
    return shown


def show_all(fcurves):
    for fc in fcurves:
        fc.hide = False
    _isolate_state.clear()


def isolate_toggle(all_curves, picked_keys):
    """Returns True if now isolated, False if restored."""
    if _isolate_state:
        for fc in all_curves:
            key = common.curve_key(fc)
            if key in _isolate_state:
                fc.hide = _isolate_state[key]
        _isolate_state.clear()
        return False
    for fc in all_curves:
        key = common.curve_key(fc)
        _isolate_state[key] = fc.hide
        fc.hide = key not in picked_keys
    return True


def is_isolated():
    return bool(_isolate_state)


# --------------------------------------------------------------------------
# Selection helpers
# --------------------------------------------------------------------------

def _set_key(k, on):
    k.select_control_point = k.select_left_handle = k.select_right_handle = on


def select_keys(fcurves, mode, scene, nth=2):
    """Returns the number of keys selected afterwards."""
    count = 0
    if mode == 'PREVIEW':
        if scene.use_preview_range:
            lo, hi = scene.frame_preview_start, scene.frame_preview_end
        else:
            lo, hi = scene.frame_start, scene.frame_end
    for fc in fcurves:
        kps = fc.keyframe_points
        if mode == 'PLAYHEAD':
            for k in kps:
                _set_key(k, abs(k.co[0] - scene.frame_current) < 0.5)
        elif mode == 'PREVIEW':
            for k in kps:
                _set_key(k, lo - 1e-4 <= k.co[0] <= hi + 1e-4)
        elif mode == 'NTH':
            picked = [k for k in kps if k.select_control_point]
            for i, k in enumerate(picked):
                _set_key(k, i % max(nth, 1) == 0)
        elif mode == 'INVERT':
            if any(k.select_control_point for k in kps):
                for k in kps:
                    _set_key(k, not k.select_control_point)
        count += sum(k.select_control_point for k in kps)
    return count


# --------------------------------------------------------------------------
# Auto frame
# --------------------------------------------------------------------------

def selection_signature(fcurves):
    parts = []
    for fc in fcurves:
        n = len(fc.keyframe_points)
        if not n:
            continue
        sel = np.zeros(n, dtype=bool)
        fc.keyframe_points.foreach_get("select_control_point", sel)
        idx = np.flatnonzero(sel)
        if len(idx):
            parts.append((common.curve_key(fc), len(idx), int(idx[0]), int(idx[-1])))
    return tuple(parts)


def _auto_frame_tick():
    try:
        wm = bpy.context.window_manager
        if common.modal_owner() is not None or wm is None:
            return AUTO_FRAME_INTERVAL
        for win in wm.windows:
            scene = win.scene
            if scene is None or not scene.mge_settings.auto_frame:
                continue
            for area in win.screen.areas:
                if area.type != 'GRAPH_EDITOR':
                    continue
                region = common.window_region(area)
                with bpy.context.temp_override(window=win, area=area, region=region):
                    sig = selection_signature(common.visible_fcurves(bpy.context))
                    ptr = area.as_pointer()
                    if sig and sig != _frame_signature.get(ptr):
                        if ptr in _frame_signature:  # not on the very first look
                            bpy.ops.graph.view_selected()
                    _frame_signature[ptr] = sig
    except Exception:
        common.log_exception("auto frame")
    return AUTO_FRAME_INTERVAL


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class _Op:
    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None


class MGE_OT_channel_set_add(_Op, bpy.types.Operator):
    bl_idname = "mge.channel_set_add"
    bl_label = "Save Channel Set"
    bl_description = ("Save the selected channels (or all shown channels if none is selected) "
                      "as a named set")
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(name="Name", default="Set")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        visible = common.visible_fcurves(context)
        picked = [fc for fc in visible if _is_picked(fc)] or visible
        if not picked:
            self.report({'WARNING'}, "No channels to save")
            return {'CANCELLED'}
        st = common.get_settings(context)
        item = st.channel_sets.add()
        item.name = self.name.strip() or "Set"
        item.data = json.dumps(set_from_curves(picked))
        self.report({'INFO'}, "Saved '%s' (%d channels)" % (item.name, len(json.loads(item.data))))
        return {'FINISHED'}


class MGE_OT_channel_set_apply(_Op, bpy.types.Operator):
    bl_idname = "mge.channel_set_apply"
    bl_label = "Show Channel Set"
    bl_description = "Show only this set's channels on the selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty()

    def execute(self, context):
        st = common.get_settings(context)
        if not 0 <= self.index < len(st.channel_sets):
            return {'CANCELLED'}
        members = json.loads(st.channel_sets[self.index].data)
        shown = apply_set(object_fcurves(context), members)
        _isolate_state.clear()
        if not shown:
            self.report({'WARNING'}, "The selected objects have none of this set's channels")
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_channel_set_remove(_Op, bpy.types.Operator):
    bl_idname = "mge.channel_set_remove"
    bl_label = "Delete Channel Set"
    bl_description = "Delete this channel set"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty()

    def execute(self, context):
        st = common.get_settings(context)
        if 0 <= self.index < len(st.channel_sets):
            st.channel_sets.remove(self.index)
        return {'FINISHED'}


class MGE_OT_channels_show_all(_Op, bpy.types.Operator):
    bl_idname = "mge.channels_show_all"
    bl_label = "Show All"
    bl_description = "Show every channel of the selected objects again"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        show_all(object_fcurves(context))
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_isolate(_Op, bpy.types.Operator):
    bl_idname = "mge.isolate"
    bl_label = "Isolate"
    bl_description = "Show only the selected curves; click again to restore what was visible"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        everything = object_fcurves(context)
        if not is_isolated():
            picked = {common.curve_key(fc) for fc in common.visible_fcurves(context) if _is_picked(fc)}
            if not picked:
                self.report({'WARNING'}, "Select a curve or keys first")
                return {'CANCELLED'}
            isolate_toggle(everything, picked)
        else:
            isolate_toggle(everything, set())
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_select_keys(_Op, bpy.types.Operator):
    bl_idname = "mge.select_keys"
    bl_label = "Select Keys"
    bl_description = "Selection helper"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(items=(
        ('PLAYHEAD', "At Playhead", "Select the keys on the current frame, on every shown curve"),
        ('PREVIEW', "In Preview Range", "Select the keys inside the preview (or scene) range"),
        ('NTH', "Every Nth", "Keep every Nth selected key selected (per curve)"),
        ('INVERT', "Invert per Curve", "Invert the selection on curves that have selected keys"),
    ))

    @classmethod
    def description(cls, context, properties):
        return cls.bl_rna.properties["mode"].enum_items[properties.mode].description

    def execute(self, context):
        st = common.get_settings(context)
        n = select_keys(common.editable_fcurves(context), self.mode, context.scene, st.select_nth)
        self.report({'INFO'}, "%d key(s) selected" % n)
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_PT_channels(bpy.types.Panel):
    bl_label = "Channels & Selection"
    bl_idname = "MGE_PT_channels"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 13
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        row = layout.row(align=True)
        row.operator("mge.isolate", icon='SOLO_ON', depress=is_isolated())
        row.operator("mge.channels_show_all", icon='HIDE_OFF')
        layout.prop(st, "auto_frame")

        box = layout.box()
        row = box.row()
        row.label(text="Channel Sets")
        row.operator("mge.channel_set_add", text="", icon='ADD')
        for i, item in enumerate(st.channel_sets):
            row = box.row(align=True)
            row.operator("mge.channel_set_apply", text=item.name, icon='RESTRICT_VIEW_OFF').index = i
            row.operator("mge.channel_set_remove", text="", icon='X').index = i
        if not len(st.channel_sets):
            box.label(text="Select channels, then +")

        box = layout.box()
        box.label(text="Select Keys")
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        grid.operator("mge.select_keys", text="At Playhead").mode = 'PLAYHEAD'
        grid.operator("mge.select_keys", text="In Preview Range").mode = 'PREVIEW'
        grid.operator("mge.select_keys", text="Invert per Curve").mode = 'INVERT'
        row = box.row(align=True)
        row.operator("mge.select_keys", text="Every Nth").mode = 'NTH'
        row.prop(st, "select_nth", text="")


classes = (MGE_OT_channel_set_add, MGE_OT_channel_set_apply, MGE_OT_channel_set_remove,
           MGE_OT_channels_show_all, MGE_OT_isolate, MGE_OT_select_keys, MGE_PT_channels)


def register_tool():
    if not bpy.app.timers.is_registered(_auto_frame_tick):
        bpy.app.timers.register(_auto_frame_tick, first_interval=1.0, persistent=True)


def unregister_tool():
    if bpy.app.timers.is_registered(_auto_frame_tick):
        bpy.app.timers.unregister(_auto_frame_tick)
    _frame_signature.clear()
    _isolate_state.clear()
