"""Tool 2 - One-click tangent toolbar (Maya tangent types).

Mapping to Blender keyframe settings
------------------------------------
Spline   automatic handles, Bezier            (overshoots like Maya spline)
Clamped  auto-clamped handles, Bezier         (no overshoot, flat at extremes)
Linear   linear interpolation
Flat     horizontal handles, Bezier
Stepped  constant interpolation
Plateau  flat handles at local extremes / ends, automatic elsewhere

Sides (Maya's In / Out tangent menus)
-------------------------------------
Both  the whole key.  Interpolation belongs to the *outgoing* segment in
      Blender, so Linear / Stepped change the segment leaving each key.
In    only the left handle and the segment *entering* the key (that is the
      previous key's interpolation).  Handles are broken (Free) so the other
      side keeps its shape.
Out   only the right handle and the segment leaving the key.

Also: Break / Unify tangents, and the default tangent for new keys
(Blender's own preference).
"""

import math

import bpy

from . import common

TANGENT_TYPES = (
    ('SPLINE', "Spline", "Smooth automatic tangents", 'HANDLE_AUTO'),
    ('LINEAR', "Linear", "Straight line to the next key", 'IPO_LINEAR'),
    ('FLAT', "Flat", "Horizontal tangents", 'IPO_EASE_IN_OUT'),
    ('STEPPED', "Stepped", "Hold the value until the next key", 'IPO_CONSTANT'),
    ('PLATEAU', "Plateau", "Flat at extremes, smooth elsewhere", 'IPO_SINE'),
    ('CLAMPED', "Clamped", "Smooth, never overshooting the keys", 'HANDLE_AUTOCLAMPED'),
)
SIDES = (
    ('BOTH', "Both", "In and out tangent"),
    ('IN', "In", "Only the incoming tangent (Ctrl+click a tangent button)"),
    ('OUT', "Out", "Only the outgoing tangent (Alt+click a tangent button)"),
)

# Maya type -> (interpolation, handle type) for Blender's "new keyframe" preferences.
NEW_KEY_TYPES = (
    ('SPLINE', "Spline", "New keys: Bezier with automatic handles", 'BEZIER', 'AUTO'),
    ('CLAMPED', "Clamped", "New keys: Bezier with auto-clamped handles", 'BEZIER', 'AUTO_CLAMPED'),
    ('LINEAR', "Linear", "New keys: linear interpolation", 'LINEAR', None),
    ('STEPPED', "Stepped", "New keys: constant interpolation", 'CONSTANT', None),
    ('OTHER', "Custom", "Set elsewhere in Preferences > Animation", None, None),
)


def _is_selected(k):
    return k.select_control_point or k.select_left_handle or k.select_right_handle


def _flat_side(k, side):
    """Make one side (or both) horizontal."""
    if side == 'BOTH':
        k.handle_left_type = 'ALIGNED'
        k.handle_right_type = 'ALIGNED'
    else:
        _break(k)
    if side in ('BOTH', 'IN'):
        k.handle_left = (k.handle_left[0], k.co[1])
    if side in ('BOTH', 'OUT'):
        k.handle_right = (k.handle_right[0], k.co[1])


def _break(k):
    """Free both handles, keeping their current positions."""
    left, right = tuple(k.handle_left), tuple(k.handle_right)
    k.handle_left_type = 'FREE'
    k.handle_right_type = 'FREE'
    k.handle_left = left
    k.handle_right = right


def _set_auto(k, side, kind):
    if side in ('BOTH', 'IN'):
        k.handle_left_type = kind
    if side in ('BOTH', 'OUT'):
        k.handle_right_type = kind


def _is_extreme(kps, i):
    n = len(kps)
    if i == 0 or i == n - 1:
        return True
    y = kps[i].co[1]
    a, b = kps[i - 1].co[1], kps[i + 1].co[1]
    return (y >= a and y >= b) or (y <= a and y <= b)


def apply_tangent(fc, kind, side='BOTH'):
    """Apply a tangent type to the selected keys of `fc`; returns key count."""
    kps = fc.keyframe_points
    n = len(kps)
    sel = [i for i in range(n) if _is_selected(kps[i])]
    if not sel:
        return 0
    extremes = {i: _is_extreme(kps, i) for i in sel}  # before anything moves

    def segment(i, ipo):
        """Set the interpolation of the segment on this side of key i."""
        if side in ('BOTH', 'OUT'):
            kps[i].interpolation = ipo
        elif i > 0:  # IN: the segment entering key i belongs to key i-1
            kps[i - 1].interpolation = ipo

    for i in sel:
        k = kps[i]
        if kind in ('SPLINE', 'CLAMPED'):
            segment(i, 'BEZIER')
            _set_auto(k, side, 'AUTO' if kind == 'SPLINE' else 'AUTO_CLAMPED')
        elif kind == 'LINEAR':
            segment(i, 'LINEAR')
        elif kind == 'STEPPED':
            segment(i, 'CONSTANT')
        elif kind == 'FLAT':
            segment(i, 'BEZIER')
            _flat_side(k, side)
        elif kind == 'PLATEAU':
            segment(i, 'BEZIER')
            if extremes[i]:
                _flat_side(k, side)
            else:
                _set_auto(k, side, 'AUTO')
    fc.update()
    return len(sel)


def break_tangents(fc):
    kps = fc.keyframe_points
    count = 0
    for k in kps:
        if _is_selected(k):
            _break(k)
            count += 1
    if count:
        fc.update()
    return count


def unify_tangents(fc):
    """Make each selected key's handles collinear (Maya 'Unify Tangents').

    The common direction is the average angle of the two handles; each handle
    keeps its own length in time.  Auto handles are already unified and are
    left alone.
    """
    kps = fc.keyframe_points
    count = 0
    for k in kps:
        if not _is_selected(k):
            continue
        count += 1
        if k.handle_left_type in ('AUTO', 'AUTO_CLAMPED') and \
                k.handle_right_type in ('AUTO', 'AUTO_CLAMPED'):
            continue
        x, y = k.co
        lx, ly = k.handle_left
        rx, ry = k.handle_right
        dl, dr = x - lx, rx - x
        a_l = math.atan2(y - ly, dl) if dl > 1e-9 else 0.0
        a_r = math.atan2(ry - y, dr) if dr > 1e-9 else 0.0
        slope = math.tan(0.5 * (a_l + a_r))
        k.handle_left_type = 'ALIGNED'
        k.handle_right_type = 'ALIGNED'
        k.handle_left = (lx, y - slope * dl)
        k.handle_right = (rx, y + slope * dr)
    if count:
        fc.update()
    return count


# --------------------------------------------------------------------------
# Default tangent for new keys (Blender preference)
# --------------------------------------------------------------------------

def get_new_key_type(_self=None):
    edit = bpy.context.preferences.edit
    ipo, handle = edit.keyframe_new_interpolation_type, edit.keyframe_new_handle_type
    for idx, (_i, _l, _d, want_ipo, want_handle) in enumerate(NEW_KEY_TYPES):
        if want_ipo == ipo and (want_handle is None or want_handle == handle):
            return idx
    return len(NEW_KEY_TYPES) - 1


def set_new_key_type(_self, value):
    _i, _l, _d, ipo, handle = NEW_KEY_TYPES[value]
    if ipo is None:
        return
    edit = bpy.context.preferences.edit
    edit.keyframe_new_interpolation_type = ipo
    if handle is not None:
        edit.keyframe_new_handle_type = handle


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

def _apply_all(context, fn, *args):
    total = 0
    for fc in common.editable_fcurves(context):
        total += fn(fc, *args)
    return total


class MGE_OT_set_tangent(bpy.types.Operator):
    bl_idname = "mge.set_tangent"
    bl_label = "Set Tangent"
    bl_description = "Apply a tangent type to the selected keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.EnumProperty(
        name="Tangent", items=[(i, l, d) for i, l, d, _ in TANGENT_TYPES], default='SPLINE')
    side: bpy.props.EnumProperty(
        name="Side", items=[('PANEL', "From Panel", "Use the side chosen in the sidebar")] + list(SIDES),
        default='PANEL')

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context, fcurves_only=False)

    @classmethod
    def description(cls, context, properties):
        for i, l, d, _ in TANGENT_TYPES:
            if i == properties.kind:
                return ("%s: %s.\nApplies to the selected keyframes. "
                        "Ctrl+click: in tangent only, Alt+click: out tangent only" % (l, d))
        return cls.bl_description

    def invoke(self, context, event):
        if self.side == 'PANEL':
            if event.ctrl:
                self.side = 'IN'
            elif event.alt:
                self.side = 'OUT'
        return self.execute(context)

    def execute(self, context):
        side = self.side
        if side == 'PANEL':
            side = common.get_settings(context).tangent_side
        total = _apply_all(context, apply_tangent, self.kind, side)
        if total == 0:
            self.report({'WARNING'}, "No keyframes selected")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_break_tangents(bpy.types.Operator):
    bl_idname = "mge.break_tangents"
    bl_label = "Break"
    bl_description = "Break the tangents of the selected keys so in and out move independently"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context, fcurves_only=False)

    def execute(self, context):
        if _apply_all(context, break_tangents) == 0:
            self.report({'WARNING'}, "No keyframes selected")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_unify_tangents(bpy.types.Operator):
    bl_idname = "mge.unify_tangents"
    bl_label = "Unify"
    bl_description = "Line up the in and out tangents of the selected keys again"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context, fcurves_only=False)

    def execute(self, context):
        if _apply_all(context, unify_tangents) == 0:
            self.report({'WARNING'}, "No keyframes selected")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


# --------------------------------------------------------------------------
# UI: sidebar panel, pie menu, header row
# --------------------------------------------------------------------------

def draw_buttons(layout, columns=3):
    grid = layout.grid_flow(row_major=True, columns=columns,
                            even_columns=True, even_rows=True, align=True)
    for ident, label, _desc, icon in TANGENT_TYPES:
        grid.operator("mge.set_tangent", text=label, icon=icon).kind = ident


class MGE_PT_tangents(bpy.types.Panel):
    bl_label = "Tangents"
    bl_idname = "MGE_PT_tangents"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 1

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context, fcurves_only=False)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        layout.row().prop(st, "tangent_side", expand=True)
        draw_buttons(layout)
        row = layout.row(align=True)
        row.operator("mge.break_tangents", icon='UNLINKED')
        row.operator("mge.unify_tangents", icon='LINKED')
        layout.prop(st, "new_key_tangent", text="New Keys")


class MGE_MT_tangent_pie(bpy.types.Menu):
    bl_label = "Tangents"
    bl_idname = "MGE_MT_tangent_pie"

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context, fcurves_only=False)

    def draw(self, context):
        pie = self.layout.menu_pie()
        # pie order: W, E, S, N, NW, NE, SW, SE
        for ident in ('LINEAR', 'STEPPED', 'FLAT', 'SPLINE', 'PLATEAU', 'CLAMPED'):
            label, icon = next((l, ic) for i, l, _d, ic in TANGENT_TYPES if i == ident)
            op = pie.operator("mge.set_tangent", text=label, icon=icon)
            op.kind, op.side = ident, 'BOTH'
        pie.operator("mge.break_tangents", icon='UNLINKED')
        pie.operator("mge.unify_tangents", icon='LINKED')


def _draw_header(self, context):
    prefs = common.get_prefs()
    if prefs is None or not getattr(prefs, "show_header_tangents", False):
        return
    if not common.graph_poll(context, fcurves_only=False):
        return
    row = self.layout.row(align=True)
    for ident, label, _desc, icon in TANGENT_TYPES:
        row.operator("mge.set_tangent", text="", icon=icon).kind = ident


classes = (MGE_OT_set_tangent, MGE_OT_break_tangents, MGE_OT_unify_tangents,
           MGE_MT_tangent_pie, MGE_PT_tangents)


def register_tool():
    bpy.types.GRAPH_HT_header.append(_draw_header)


def unregister_tool():
    try:
        bpy.types.GRAPH_HT_header.remove(_draw_header)
    except Exception:
        pass
