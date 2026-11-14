"""Tool 6 - Key stats: Maya's time / value boxes for the whole selection.

Absolute mode
  Frame  shows the first selected frame; typing a frame moves the whole
         selection so its first key lands there (spacing is kept, keys
         never pile up on one frame).
  Value  shows the shared value (or the average if values differ); typing
         a value sets every selected key to it.
Relative mode
  Fields start at 0 for a new selection; typing (or dragging to) a number
  offsets every selected key by it.  The field then shows the total offset
  applied to this selection.

Rotation values are shown in degrees when every selected key is on a
rotation curve (and the scene uses degrees), like the Graph Editor does.
Handles travel with their keys.
"""

import math

import bpy

from . import common


def selection(context=None):
    """[(fc, [indices])] of selected keys on editable visible curves."""
    context = context or bpy.context
    out = []
    for fc in common.editable_fcurves(context):
        idx = [i for i, k in enumerate(fc.keyframe_points) if k.select_control_point]
        if idx:
            out.append((fc, idx))
    return out


def value_scale(sel, scene):
    """Factor raw -> shown value: degrees only if *all* curves are angles."""
    if sel and scene.unit_settings.system_rotation == 'DEGREES' and \
            all(common.curve_is_angle(fc) for fc, _ in sel):
        return 180.0 / math.pi
    return 1.0


def summary(context=None):
    context = context or bpy.context
    sel = selection(context)
    frames = [fc.keyframe_points[i].co[0] for fc, idx in sel for i in idx]
    values = [fc.keyframe_points[i].co[1] for fc, idx in sel for i in idx]
    return sel, frames, values


def move_keys(sel, dx=0.0, dy=None, set_y=None):
    """Offset selected keys (and their handles) by dx / dy, or set y."""
    for fc, idx in sel:
        kps = fc.keyframe_points
        for i in idx:
            k = kps[i]
            x, y = k.co
            ny = set_y if set_y is not None else y + (dy or 0.0)
            ddy = ny - y
            k.co = (x + dx, ny)
            k.handle_left = (k.handle_left[0] + dx, k.handle_left[1] + ddy)
            k.handle_right = (k.handle_right[0] + dx, k.handle_right[1] + ddy)
        fc.update()
    common.redraw_graph_editors()


# --- property callbacks (registered on MGE_Settings in core.py) -------------
#
# Relative fields show the offset applied so far to the current selection, so
# dragging a field (which sends the running total) doesn't compound offsets.
_rel = {"sig": None, "frame": 0.0, "value": 0.0}


def _relative(sel, name):
    sig = tuple((common.curve_key(fc), tuple(idx)) for fc, idx in sel)
    if sig != _rel["sig"]:
        _rel.update(sig=sig, frame=0.0, value=0.0)
    return _rel[name]


def _relative_set(name, value):
    delta = value - _rel[name]
    _rel[name] = value
    return delta


def get_frame(self):
    if self.stats_mode == 'RELATIVE':
        try:
            return _relative(selection(), "frame")
        except Exception:
            return 0.0
    try:
        _sel, frames, _v = summary()
    except Exception:
        return 0.0
    return min(frames) if frames else 0.0


def set_frame(self, value):
    sel, frames, _v = summary()
    if not frames:
        return
    if self.stats_mode == 'RELATIVE':
        _relative(sel, "frame")
        dx = _relative_set("frame", value)
    else:
        dx = value - min(frames)
    if dx:
        move_keys(sel, dx=dx)


def get_value(self):
    if self.stats_mode == 'RELATIVE':
        try:
            return _relative(selection(), "value")
        except Exception:
            return 0.0
    try:
        sel, _f, values = summary()
    except Exception:
        return 0.0
    if not values:
        return 0.0
    return sum(values) / len(values) * value_scale(sel, bpy.context.scene)


def set_value(self, value):
    sel, _f, values = summary()
    if not values:
        return
    scale = value_scale(sel, bpy.context.scene)
    if self.stats_mode == 'RELATIVE':
        _relative(sel, "value")
        delta = _relative_set("value", value) / scale
        if delta:
            move_keys(sel, dy=delta)
    else:
        move_keys(sel, set_y=value / scale)


class MGE_PT_stats(bpy.types.Panel):
    bl_label = "Key Stats"
    bl_idname = "MGE_PT_stats"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 0

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        sel, frames, values = summary(context)
        layout.row().prop(st, "stats_mode", expand=True)
        if not frames:
            layout.label(text="No keyframes selected")
            return
        col = layout.column(align=True)
        col.prop(st, "stats_frame", text="Frame")
        col.prop(st, "stats_value", text="Value")
        n_keys = len(frames)
        layout.label(text="%d key%s, %d curve%s" % (n_keys, "" if n_keys == 1 else "s",
                                                   len(sel), "" if len(sel) == 1 else "s"))
        if st.stats_mode == 'ABSOLUTE' and max(values) - min(values) > 1e-6:
            layout.label(text="Values differ: average shown", icon='INFO')
        if value_scale(sel, context.scene) != 1.0:
            layout.label(text="Rotation shown in degrees", icon='INFO')


classes = (MGE_PT_stats,)


def register_tool():
    pass


def unregister_tool():
    pass
