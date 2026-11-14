"""Tool 1 - Buffer / Ghost Curve.

Snapshots live in memory (never touch the F-Curves) and are drawn by a
POST_PIXEL draw handler on top of the Graph Editor.  Because they are only
pixels, they can't be selected or interfere with editing the real keys.
"""

import bpy

from . import common

# key -> Buffer
_buffers = {}
_handle = None


class Buffer:
    __slots__ = ("samples", "keys")

    def __init__(self, samples, keys):
        self.samples = samples  # (n, 2) raw frame/value samples
        self.keys = keys        # CurveSnapshot, used by "swap"


def buffer_count():
    return len(_buffers)


def clear_buffers():
    _buffers.clear()


def take_snapshot(fcurves):
    """Store a buffer for each F-Curve. Returns the number stored."""
    count = 0
    for fc in fcurves:
        samples = common.sample_curve(fc)
        if samples is None:
            continue
        _buffers[common.curve_key(fc)] = Buffer(samples, common.CurveSnapshot.of(fc))
        count += 1
    return count


def swap_with_buffer(fcurves):
    """Maya's 'swap buffer curve': the curve takes the buffered shape and the
    shape it had becomes the new buffer."""
    count = 0
    for fc in fcurves:
        key = common.curve_key(fc)
        buf = _buffers.get(key)
        if buf is None:
            continue
        current_samples = common.sample_curve(fc)
        current_keys = common.CurveSnapshot.of(fc)
        buf.keys.write(fc)
        _buffers[key] = Buffer(current_samples, current_keys)
        count += 1
    return count


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class _GhostOp:
    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)


class MGE_OT_ghost_snapshot(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_snapshot"
    bl_label = "Snapshot"
    bl_description = ("Store the current shape of the selected curves (or all "
                      "visible curves if none is selected) as a ghost to compare against")
    bl_options = {'INTERNAL'}

    def execute(self, context):
        curves = common.selected_visible_fcurves(context) or common.visible_fcurves(context)
        n = take_snapshot(curves)
        if n == 0:
            self.report({'WARNING'}, "No curves with keyframes to snapshot")
            return {'CANCELLED'}
        common.get_settings(context).ghost_show = True
        self.report({'INFO'}, "Ghost stored for %d curve(s)" % n)
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_ghost_clear(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_clear"
    bl_label = "Clear"
    bl_description = "Remove all stored ghost curves"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        clear_buffers()
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_ghost_swap(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_swap"
    bl_label = "Swap"
    bl_description = ("Swap the selected curves with their ghost: the curve "
                      "returns to the snapshot shape and its current shape becomes the ghost")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        curves = common.selected_visible_fcurves(context) or common.editable_fcurves(context)
        n = swap_with_buffer(curves)
        if n == 0:
            self.report({'WARNING'}, "No ghost stored for the selected curves")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def _draw():
    if not _buffers:
        return
    ctx = bpy.context
    space, region, scene = ctx.space_data, ctx.region, ctx.scene
    if (space is None or space.type != 'GRAPH_EDITOR' or space.mode != 'FCURVES'
            or region is None or scene is None):
        return
    settings = scene.mge_settings
    if not settings.ghost_show:
        return
    try:
        curves = common.visible_fcurves(ctx)
        if not curves:
            return
        ox, oy, sx, sy = common.view_affine(region)
        tscale = common.time_scale(space, scene)
        color = tuple(settings.ghost_color)
        for fc in curves:
            buf = _buffers.get(common.curve_key(fc))
            if buf is None:
                continue
            scale, offset = common.display_mapping(fc, space, scene)
            s = buf.samples
            px = ox + s[:, 0] * tscale * sx
            py = oy + (s[:, 1] + offset) * scale * sy
            common.draw_polyline(zip(px.tolist(), py.tolist()), color,
                                 settings.ghost_width)
    except Exception:
        common.log_exception("ghost draw")


def register_tool():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceGraphEditor.draw_handler_add(
            _draw, (), 'WINDOW', 'POST_PIXEL')
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)
    common.redraw_graph_editors()


def unregister_tool():
    global _handle
    if _handle is not None:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    clear_buffers()
    common.redraw_graph_editors()


@bpy.app.handlers.persistent
def _on_load(_dummy=None):
    clear_buffers()
    common.clear_caches()


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------

class MGE_PT_ghost(bpy.types.Panel):
    bl_label = "Buffer Curve"
    bl_idname = "MGE_PT_ghost"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 2

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("mge.ghost_snapshot", icon='FCURVE_SNAPSHOT')
        row.operator("mge.ghost_clear", icon='X')
        layout.operator("mge.ghost_swap", icon='ARROW_LEFTRIGHT')
        n = buffer_count()
        layout.label(text="%d curve(s) buffered" % n if n else "No buffer stored")
        col = layout.column(align=True)
        col.prop(st, "ghost_show", text="Show Ghost", toggle=True,
                 icon='HIDE_OFF' if st.ghost_show else 'HIDE_ON')
        col.prop(st, "ghost_color", text="")
        col.prop(st, "ghost_width")


classes = (MGE_OT_ghost_snapshot, MGE_OT_ghost_clear, MGE_OT_ghost_swap,
           MGE_PT_ghost)
