"""Tool 5 - Curves: one-click Pre/Post Infinity and Euler filter.

Maya's infinity modes map onto Blender like this:

  Constant / Linear          F-Curve extrapolation
  Cycle                      Cycles modifier, Repeat
  Cycle with Offset          Cycles modifier, Repeat with Offset
  Oscillate                  Cycles modifier, Repeat Mirrored

Blender keeps a single Constant/Linear extrapolation for both ends, so
choosing Constant or Linear for one side also changes the other side when
that side isn't cycling (the operator says so when it happens).
"""

import bpy

from . import common

INFINITY_MODES = (
    ('CONSTANT', "Constant", "Hold the first/last value", 'IPO_CONSTANT'),
    ('LINEAR', "Linear", "Continue in the direction of the end tangent", 'IPO_LINEAR'),
    ('CYCLE', "Cycle", "Repeat the curve", 'FILE_REFRESH'),
    ('CYCLE_OFFSET', "Offset", "Repeat, each cycle starting where the last ended", 'FORCE_HARMONIC'),
    ('OSCILLATE', "Oscillate", "Repeat back and forth (mirrored)", 'IPO_ELASTIC'),
)
_CYCLE_MODE = {'CYCLE': 'REPEAT', 'CYCLE_OFFSET': 'REPEAT_OFFSET', 'OSCILLATE': 'MIRROR'}
_FROM_CYCLE = {v: k for k, v in _CYCLE_MODE.items()}


def _cycles_modifier(fc, create=False):
    for m in fc.modifiers:
        if m.type == 'CYCLES':
            return m
    if create:
        return fc.modifiers.new(type='CYCLES')
    return None


def _attr(side):
    return "mode_before" if side == 'PRE' else "mode_after"


def get_infinity(fc, side):
    """Current Maya-style infinity mode of one side of a curve."""
    mod = _cycles_modifier(fc)
    if mod is not None and not mod.mute:
        mode = getattr(mod, _attr(side))
        if mode in _FROM_CYCLE:
            return _FROM_CYCLE[mode]
    return 'LINEAR' if fc.extrapolation == 'LINEAR' else 'CONSTANT'


def set_infinity(fc, side, mode):
    """side: 'PRE' | 'POST' | 'BOTH'.  Returns True if the other side's
    Constant/Linear setting changed too (Blender shares it)."""
    sides = ('PRE', 'POST') if side == 'BOTH' else (side,)
    others = [s for s in ('PRE', 'POST') if s not in sides]
    shared_changed = False
    mod = _cycles_modifier(fc)
    if mode in _CYCLE_MODE:
        if mod is None:
            mod = _cycles_modifier(fc, create=True)
            for s in ('PRE', 'POST'):
                setattr(mod, _attr(s), 'NONE')
        mod.mute = False
        for s in sides:
            setattr(mod, _attr(s), _CYCLE_MODE[mode])
    else:
        before = {s: get_infinity(fc, s) for s in others}
        fc.extrapolation = mode
        if mod is not None:
            for s in sides:
                setattr(mod, _attr(s), 'NONE')
        shared_changed = any(get_infinity(fc, s) != before[s] for s in others)
    if (mod is not None and mod.mode_before == 'NONE' and mod.mode_after == 'NONE'
            and not mod.use_restricted_range and not mod.use_influence):
        fc.modifiers.remove(mod)
    fc.update()
    return shared_changed


def target_fcurves(context):
    """Curves selected in the channel list or having selected keys."""
    out = []
    for fc in common.editable_fcurves(context):
        if fc.select or any(k.select_control_point for k in fc.keyframe_points):
            out.append(fc)
    return out


class MGE_OT_set_infinity(bpy.types.Operator):
    bl_idname = "mge.set_infinity"
    bl_label = "Set Infinity"
    bl_description = "Set how the selected curves continue before their first / after their last key"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(items=(('PRE', "Pre", ""), ('POST', "Post", ""),
                                        ('BOTH', "Both", "")), default='BOTH')
    mode: bpy.props.EnumProperty(items=[(i, l, d) for i, l, d, _ in INFINITY_MODES])

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    @classmethod
    def description(cls, context, properties):
        side = {"PRE": "Pre-infinity", "POST": "Post-infinity", "BOTH": "Pre and post infinity"}
        for i, l, d, _ in INFINITY_MODES:
            if i == properties.mode:
                return "%s: %s (%s)" % (side[properties.side], l, d)
        return cls.bl_description

    def execute(self, context):
        curves = target_fcurves(context)
        if not curves:
            self.report({'WARNING'}, "Select curves or keyframes first")
            return {'CANCELLED'}
        shared = sum(set_infinity(fc, self.side, self.mode) for fc in curves)
        if shared:
            self.report({'INFO'}, "Blender shares Constant/Linear between both ends: "
                        "changed on %d curve(s)" % shared)
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_PT_curves(bpy.types.Panel):
    bl_label = "Curves"
    bl_idname = "MGE_PT_curves"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 6

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        active = context.active_editable_fcurve if hasattr(context, "active_editable_fcurve") else None
        col = layout.column(align=True)
        for side, label in (('PRE', "Pre Infinity"), ('POST', "Post Infinity")):
            col.label(text=label)
            row = col.row(align=True)
            current = get_infinity(active, side) if active else None
            for ident, text, _d, icon in INFINITY_MODES:
                op = row.operator("mge.set_infinity", text="", icon=icon, depress=(ident == current))
                op.side, op.mode = side, ident
        row = layout.row(align=True)
        row.label(text="Both:")
        for ident, text, _d, icon in INFINITY_MODES:
            op = row.operator("mge.set_infinity", text="", icon=icon)
            op.side, op.mode = 'BOTH', ident
        space = context.space_data
        layout.prop(space, "show_extrapolation", text="Show Extrapolation")
        layout.separator()
        layout.operator("graph.euler_filter", text="Euler Filter", icon='DRIVER_ROTATIONAL_DIFFERENCE')


classes = (MGE_OT_set_infinity, MGE_PT_curves)


def register_tool():
    pass


def unregister_tool():
    pass
