"""Tool 1 - Buffer / Ghost Curve.

Snapshots never touch the F-Curves while you work: they're drawn by a
POST_PIXEL draw handler on top of the Graph Editor, so they can't be selected
or interfere with editing the real keys.

* Three slots (A, B, C), each with its own colour and visibility.
* Ghost range: the curve's key range, or the scene frame range (handy to
  see cycles / extrapolation).
* Solid or dashed lines.
* Optionally saved in the .blend: written onto each action as a custom
  property when the file is saved, read back when it is opened.
"""

import json

import bpy
import numpy as np

from . import common
from .i18n import iface

SLOTS = ('A', 'B', 'C')
PROP = "mge_ghosts"

# (slot, curve key) -> Buffer
_buffers = {}
_handle = None
_needs_load = True   # ghosts saved in the open file not read yet (bpy.data is
                     # restricted while add-ons register, so it's done on first use)


def ensure_loaded():
    global _needs_load
    if _needs_load:
        _needs_load = False
        try:
            if not _buffers:
                load_from_actions()
        except Exception:
            common.log_exception("loading ghosts")


class Buffer:
    __slots__ = ("samples", "keys")

    def __init__(self, samples, keys):
        self.samples = samples  # (n, 2) raw frame/value samples
        self.keys = keys        # CurveSnapshot, used by "swap"


def buffer_count(slot=None):
    ensure_loaded()
    return sum(1 for (s, _k) in _buffers if slot is None or s == slot)


def clear_buffers(slot=None):
    for key in [k for k in _buffers if slot is None or k[0] == slot]:
        del _buffers[key]


def _sample_range(fc, scene, settings):
    if settings is not None and settings.ghost_range == 'SCENE' and scene is not None:
        if scene.use_preview_range:
            return scene.frame_preview_start, scene.frame_preview_end
        return scene.frame_start, scene.frame_end
    return None


def take_snapshot(fcurves, slot='A', scene=None, settings=None):
    """Store a buffer for each F-Curve in `slot`. Returns the number stored."""
    ensure_loaded()
    count = 0
    for fc in fcurves:
        rng = _sample_range(fc, scene, settings)
        samples = common.sample_curve(fc, frame_range=rng)
        if samples is None:
            continue
        _buffers[(slot, common.curve_key(fc))] = Buffer(samples, common.CurveSnapshot.of(fc))
        count += 1
    return count


def swap_with_buffer(fcurves, slot='A', scene=None, settings=None):
    """Maya's 'swap buffer curve': the curve takes the buffered shape and the
    shape it had becomes the new buffer."""
    ensure_loaded()
    count = 0
    for fc in fcurves:
        key = (slot, common.curve_key(fc))
        buf = _buffers.get(key)
        if buf is None:
            continue
        current_samples = common.sample_curve(fc, frame_range=_sample_range(fc, scene, settings))
        current_keys = common.CurveSnapshot.of(fc)
        buf.keys.write(fc)
        _buffers[key] = Buffer(current_samples, current_keys)
        count += 1
    return count


def snapshot_from_action(fcurves, source_action, slot='A', scene=None, settings=None):
    """Ghost each curve with the matching channel (same path and index) of
    another action, e.g. a mocap reference or an earlier take."""
    by_channel = {(fc.data_path, fc.array_index): fc for fc in common.action_fcurves(source_action)}
    count = 0
    for fc in fcurves:
        src = by_channel.get((fc.data_path, fc.array_index))
        if src is None or src == fc:
            continue
        samples = common.sample_curve(src, frame_range=_sample_range(src, scene, settings))
        if samples is None:
            continue
        _buffers[(slot, common.curve_key(fc))] = Buffer(samples, common.CurveSnapshot.of(src))
        count += 1
    return count


def swap_range_with_buffer(fcurves, slot='A'):
    """Swap only the time range of the selected keys with the buffer."""
    ensure_loaded()
    count = 0
    for fc in fcurves:
        key = (slot, common.curve_key(fc))
        buf = _buffers.get(key)
        if buf is None:
            continue
        current = common.CurveSnapshot.of(fc)
        if not current.selected.any():
            continue
        xs = current.co[current.selected, 0]
        x0, x1 = float(xs.min()), float(xs.max())
        cur_part = common.sample_curve(fc, frame_range=(x0, x1))
        new_curve = current.splice(buf.keys, x0, x1)
        new_buffer_keys = buf.keys.splice(current, x0, x1)
        s = buf.samples
        outside = s[(s[:, 0] < x0) | (s[:, 0] > x1)]
        merged = np.concatenate([outside, cur_part]) if cur_part is not None else outside
        merged = merged[np.argsort(merged[:, 0], kind="stable")]
        new_curve.write(fc)
        _buffers[key] = Buffer(merged, new_buffer_keys)
        count += 1
    return count


PALETTES = {
    # grey / orange / magenta: clear of Blender's red, green, blue channel colours
    'DEFAULT': ((0.85, 0.85, 0.85, 0.55), (1.0, 0.55, 0.15, 0.65), (0.95, 0.35, 0.95, 0.65)),
    # Okabe-Ito yellow / reddish purple / white: distinguishable with the common
    # forms of colour blindness, and from the channel colours
    'CB_SAFE': ((0.94, 0.89, 0.26, 0.8), (0.80, 0.47, 0.65, 0.85), (1.0, 1.0, 1.0, 0.7)),
}


# --------------------------------------------------------------------------
# Saving in the .blend
# --------------------------------------------------------------------------

def _snap_to_props(snap):
    return {
        "co": snap.co.ravel().tolist(), "hl": snap.hl.ravel().tolist(),
        "hr": snap.hr.ravel().tolist(),
        "meta": json.dumps({"n": snap.n, "enums": snap.enums, "floats": snap.floats,
                            "bools": snap.bools, "extrapolation": snap.extrapolation}),
    }


def _snap_from_props(group):
    meta = json.loads(group["meta"])
    snap = common.CurveSnapshot()
    n = meta["n"]
    snap.n = n
    snap.co = np.array(group["co"], dtype=np.float64).reshape(n, 2)
    snap.hl = np.array(group["hl"], dtype=np.float64).reshape(n, 2)
    snap.hr = np.array(group["hr"], dtype=np.float64).reshape(n, 2)
    snap.enums, snap.floats, snap.bools = meta["enums"], meta["floats"], meta["bools"]
    snap.extrapolation = meta["extrapolation"]
    return snap


def store_in_actions(enabled=True):
    """Write buffers onto their actions (and remove stale ones)."""
    ensure_loaded()  # never drop ghosts that were saved but not read yet
    by_action = {}
    if enabled:
        for (slot, (action_name, path, index)), buf in _buffers.items():
            by_action.setdefault(action_name, {})["%s|%d|%s" % (slot, index, path)] = buf
    for action in bpy.data.actions:
        if action.library is not None:
            continue
        entries = by_action.get(action.name_full)
        if not entries:
            if PROP in action:
                del action[PROP]
            continue
        data = {}
        for name, buf in entries.items():
            group = _snap_to_props(buf.keys)
            group["samples"] = buf.samples.ravel().tolist()
            data[name] = group
        action[PROP] = data


def load_from_actions():
    """Rebuild buffers from the actions of the current file."""
    global _needs_load
    _needs_load = False
    clear_buffers()
    for action in bpy.data.actions:
        data = action.get(PROP)
        if not data:
            continue
        for name, group in data.items():
            try:
                slot, index, path = name.split("|", 2)
                samples = np.array(group["samples"], dtype=np.float64).reshape(-1, 2)
                _buffers[(slot, (action.name_full, path, int(index)))] = Buffer(
                    samples, _snap_from_props(group))
            except Exception:
                common.log_exception("loading ghost '%s'" % name)


@bpy.app.handlers.persistent
def _on_save_pre(_dummy=None):
    try:
        scene = bpy.context.scene
        store_in_actions(enabled=scene is None or scene.mge_settings.ghost_save)
    except Exception:
        common.log_exception("saving ghosts")


@bpy.app.handlers.persistent
def _on_load_post(_dummy=None):
    common.clear_caches()
    try:
        load_from_actions()
    except Exception:
        common.log_exception("loading ghosts")
    common.redraw_graph_editors()


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

_SLOT_ITEMS = [('ACTIVE', "Active", "The slot chosen in the panel")] + \
    [(s, s, "Slot " + s) for s in SLOTS]


def _resolve_slot(context, slot):
    return common.get_settings(context).ghost_slot if slot == 'ACTIVE' else slot


class _GhostOp:
    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)


class MGE_OT_ghost_snapshot(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_snapshot"
    bl_label = "Snapshot"
    bl_description = ("Store the current shape of the selected curves (or all "
                      "visible curves if none is selected) as a ghost in the active slot")
    bl_options = {'INTERNAL'}

    slot: bpy.props.EnumProperty(items=_SLOT_ITEMS, default='ACTIVE')

    def execute(self, context):
        st = common.get_settings(context)
        slot = _resolve_slot(context, self.slot)
        curves = common.selected_visible_fcurves(context) or common.visible_fcurves(context)
        n = take_snapshot(curves, slot, context.scene, st)
        if n == 0:
            self.report({'WARNING'}, "No curves with keyframes to snapshot")
            return {'CANCELLED'}
        st.ghost_show = True
        setattr(st, "ghost_show_" + slot.lower(), True)
        self.report({'INFO'}, "Ghost %s stored for %d curve(s)" % (slot, n))
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_ghost_clear(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_clear"
    bl_label = "Clear"
    bl_description = "Remove the ghosts of the active slot (all slots with 'Clear All')"
    bl_options = {'INTERNAL'}

    slot: bpy.props.EnumProperty(items=_SLOT_ITEMS + [('ALL', "All", "Every slot")],
                                 default='ACTIVE')

    def execute(self, context):
        clear_buffers(None if self.slot == 'ALL' else _resolve_slot(context, self.slot))
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_ghost_swap(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_swap"
    bl_label = "Swap"
    bl_description = ("Swap the selected curves with their ghost in the active slot: the curve "
                      "returns to the snapshot shape and its current shape becomes the ghost")
    bl_options = {'REGISTER', 'UNDO'}

    slot: bpy.props.EnumProperty(items=_SLOT_ITEMS, default='ACTIVE')

    def execute(self, context):
        slot = _resolve_slot(context, self.slot)
        curves = common.selected_visible_fcurves(context) or common.editable_fcurves(context)
        n = swap_with_buffer(curves, slot, context.scene, common.get_settings(context))
        if n == 0:
            self.report({'WARNING'}, "No ghost in slot %s for the selected curves" % slot)
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_ghost_from_action(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_from_action"
    bl_label = "Ghost from Action"
    bl_description = ("Show the matching channels of another action (a reference, mocap or an "
                      "earlier take) as ghosts in the active slot")
    bl_options = {'INTERNAL'}

    def execute(self, context):
        st = common.get_settings(context)
        if st.ghost_source is None:
            self.report({'WARNING'}, "Pick a source action first")
            return {'CANCELLED'}
        curves = common.selected_visible_fcurves(context) or common.visible_fcurves(context)
        n = snapshot_from_action(curves, st.ghost_source, st.ghost_slot, context.scene, st)
        if n == 0:
            self.report({'WARNING'}, "'%s' has no channels matching the shown curves"
                        % st.ghost_source.name)
            return {'CANCELLED'}
        st.ghost_show = True
        setattr(st, "ghost_show_" + st.ghost_slot.lower(), True)
        self.report({'INFO'}, "Ghost %s: %d curve(s) from '%s'" % (st.ghost_slot, n, st.ghost_source.name))
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_ghost_swap_range(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_swap_range"
    bl_label = "Swap Range"
    bl_description = ("Swap only the time range of the selected keys with the ghost in the "
                      "active slot, leaving the rest of the curve alone")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        slot = common.get_settings(context).ghost_slot
        n = swap_range_with_buffer(common.editable_fcurves(context), slot)
        if n == 0:
            self.report({'WARNING'}, "Select keys on a curve that has a ghost in slot %s" % slot)
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_ghost_palette(_GhostOp, bpy.types.Operator):
    bl_idname = "mge.ghost_palette"
    bl_label = "Ghost Palette"
    bl_description = "Set the three ghost colours to a preset palette"
    bl_options = {'INTERNAL'}

    palette: bpy.props.EnumProperty(items=(
        ('DEFAULT', "Default", "Grey, orange, magenta"),
        ('CB_SAFE', "Colour-Blind Safe", "Yellow, purple and white, distinguishable with the "
                                         "common forms of colour blindness"),
    ))

    def execute(self, context):
        st = common.get_settings(context)
        for slot, colour in zip(SLOTS, PALETTES[self.palette]):
            setattr(st, "ghost_color_" + slot.lower(), colour)
        common.redraw_graph_editors()
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def dash_segments(px, py, dash=8.0, gap=6.0):
    """Split a pixel polyline into dash segments [(x0, y0, x1, y1), ...]."""
    if len(px) < 2:
        return []
    seg = np.hypot(np.diff(px), np.diff(py))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total <= 0:
        return []
    t = np.arange(0.0, total, 2.0)  # resample every 2 px
    rx, ry = np.interp(t, cum, px), np.interp(t, cum, py)
    on = (t % (dash + gap)) < dash
    keep = on[:-1] & on[1:]
    return list(zip(rx[:-1][keep], ry[:-1][keep], rx[1:][keep], ry[1:][keep]))


def _draw():
    if not common.tool_enabled("ghost"):
        return
    ensure_loaded()
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
        for slot in SLOTS:
            if not getattr(settings, "ghost_show_" + slot.lower()):
                continue
            color = tuple(getattr(settings, "ghost_color_" + slot.lower()))
            for fc in curves:
                buf = _buffers.get((slot, common.curve_key(fc)))
                if buf is None:
                    continue
                scale, offset = common.display_mapping(fc, space, scene)
                s = buf.samples
                nscale, noff = common.nla_mapping(fc)
                px = ox + (s[:, 0] * nscale + noff) * tscale * sx
                py = oy + (s[:, 1] + offset) * scale * sy
                if settings.ghost_style == 'DASHED':
                    common.draw_segments(dash_segments(px, py), color, settings.ghost_width)
                else:
                    common.draw_polyline(zip(px.tolist(), py.tolist()), color,
                                         settings.ghost_width)
    except Exception:
        common.log_exception("ghost draw")


def register_tool():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceGraphEditor.draw_handler_add(
            _draw, (), 'WINDOW', 'POST_PIXEL')
    for handlers, fn in ((bpy.app.handlers.load_post, _on_load_post),
                         (bpy.app.handlers.save_pre, _on_save_pre)):
        if fn not in handlers:
            handlers.append(fn)
    global _needs_load
    _needs_load = True  # ghosts saved in the open file are read on first use
    common.redraw_graph_editors()


def unregister_tool():
    global _handle
    if _handle is not None:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    for handlers, fn in ((bpy.app.handlers.load_post, _on_load_post),
                         (bpy.app.handlers.save_pre, _on_save_pre)):
        if fn in handlers:
            handlers.remove(fn)
    clear_buffers()
    common.redraw_graph_editors()


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
        layout.row().prop(st, "ghost_slot", expand=True)
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("mge.ghost_snapshot", icon='FCURVE_SNAPSHOT')
        row.operator("mge.ghost_swap", icon='ARROW_LEFTRIGHT')
        row = layout.row(align=True)
        row.operator("mge.ghost_swap_range", icon='UV_SYNC_SELECT')
        row.operator("mge.ghost_clear", icon='X')
        row.operator("mge.ghost_clear", text="", icon='TRASH').slot = 'ALL'
        row = layout.row(align=True)
        row.prop(st, "ghost_source", text="")
        row.operator("mge.ghost_from_action", text="", icon='IMPORT')

        layout.prop(st, "ghost_show", text="Show Ghosts", toggle=True,
                    icon='HIDE_OFF' if st.ghost_show else 'HIDE_ON')
        col = layout.column(align=True)
        col.active = st.ghost_show
        for slot in SLOTS:
            low = slot.lower()
            row = col.row(align=True)
            shown = getattr(st, "ghost_show_" + low)
            row.prop(st, "ghost_show_" + low, text="", icon='HIDE_OFF' if shown else 'HIDE_ON')
            row.prop(st, "ghost_color_" + low, text="")
            n = buffer_count(slot)
            row.label(text=iface("{slot}: {count} curves").format(slot=slot, count=n),
                      translate=False)
        col = layout.column()
        col.prop(st, "ghost_width")
        col.row().prop(st, "ghost_style", expand=True)
        row = col.row(align=True)
        row.label(text="Range")
        row.prop(st, "ghost_range", text="")
        col.prop(st, "ghost_save")
        col.operator_menu_enum("mge.ghost_palette", "palette", text="Colour Palette")


classes = (MGE_OT_ghost_snapshot, MGE_OT_ghost_clear, MGE_OT_ghost_swap,
           MGE_OT_ghost_from_action, MGE_OT_ghost_swap_range, MGE_OT_ghost_palette,
           MGE_PT_ghost)
