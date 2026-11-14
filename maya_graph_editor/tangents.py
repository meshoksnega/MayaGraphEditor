"""Tool 2 - One-click tangent toolbar (Maya tangent types).

Mapping to Blender keyframe settings
------------------------------------
Spline   automatic handles, Bezier            (overshoots like Maya spline)
Clamped  auto-clamped handles, Bezier         (no overshoot, flat at extremes)
Linear   linear interpolation
Flat     horizontal handles (aligned), Bezier
Stepped  constant interpolation
Plateau  flat handles at local extremes / ends, automatic elsewhere

Interpolation in Blender belongs to the *outgoing* segment of a key, so
Linear / Stepped change the segment that leaves each selected key.
"""

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


def _is_selected(k):
    return k.select_control_point or k.select_left_handle or k.select_right_handle


def _set_flat(k):
    k.handle_left_type = 'ALIGNED'
    k.handle_right_type = 'ALIGNED'
    k.handle_left = (k.handle_left[0], k.co[1])
    k.handle_right = (k.handle_right[0], k.co[1])


def apply_tangent(fc, kind):
    """Apply a tangent type to the selected keys of `fc`; returns key count."""
    kps = fc.keyframe_points
    n = len(kps)
    changed = 0
    for i in range(n):
        k = kps[i]
        if not _is_selected(k):
            continue
        changed += 1
        if kind == 'SPLINE':
            k.interpolation = 'BEZIER'
            k.handle_left_type = k.handle_right_type = 'AUTO'
        elif kind == 'CLAMPED':
            k.interpolation = 'BEZIER'
            k.handle_left_type = k.handle_right_type = 'AUTO_CLAMPED'
        elif kind == 'LINEAR':
            k.interpolation = 'LINEAR'
        elif kind == 'STEPPED':
            k.interpolation = 'CONSTANT'
        elif kind == 'FLAT':
            k.interpolation = 'BEZIER'
            _set_flat(k)
        elif kind == 'PLATEAU':
            k.interpolation = 'BEZIER'
            y = k.co[1]
            if i == 0 or i == n - 1:
                extreme = True
            else:
                a, b = kps[i - 1].co[1], kps[i + 1].co[1]
                extreme = (y >= a and y >= b) or (y <= a and y <= b)
            if extreme:
                _set_flat(k)
            else:
                k.handle_left_type = k.handle_right_type = 'AUTO'
    if changed:
        fc.update()
    return changed


class MGE_OT_set_tangent(bpy.types.Operator):
    bl_idname = "mge.set_tangent"
    bl_label = "Set Tangent"
    bl_description = "Apply a tangent type to the selected keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.EnumProperty(
        name="Tangent",
        items=[(i, l, d) for i, l, d, _ in TANGENT_TYPES],
        default='SPLINE',
    )

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context, fcurves_only=False)

    @classmethod
    def description(cls, context, properties):
        for i, l, d, _ in TANGENT_TYPES:
            if i == properties.kind:
                return "%s: %s (applies to selected keyframes)" % (l, d)
        return cls.bl_description

    def execute(self, context):
        total = 0
        for fc in common.editable_fcurves(context):
            total += apply_tangent(fc, self.kind)
        if total == 0:
            self.report({'WARNING'}, "No keyframes selected")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


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
        grid = self.layout.grid_flow(row_major=True, columns=3,
                                     even_columns=True, even_rows=True, align=True)
        for ident, label, _desc, icon in TANGENT_TYPES:
            op = grid.operator("mge.set_tangent", text=label, icon=icon)
            op.kind = ident


classes = (MGE_OT_set_tangent, MGE_PT_tangents)


def register_tool():
    pass


def unregister_tool():
    pass
