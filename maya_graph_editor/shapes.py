"""Tool - Shape library and Maya-style copy / paste.

Shape Library
    Save the shape of the selected keys (a nice ease, an overshoot, a
    bounce) under a name and apply it to other keys later: the shape is
    stretched between the first and last selected key, in time and value.
    A few shapes are built in; your own are stored in Blender's user folder,
    so they are available in every file.
Copy / Paste Keys
    Copy the selected keys, then paste at the playhead with Maya's options:
      Merge     add to what is there (keys on the same frame are replaced)
      Replace   remove the existing keys in the pasted time range first
      Insert    push later keys back to make room
      Fit       stretch the copied keys to fill the selected keys' time range
    "Relative Values" offsets the pasted values so they start from the
    curve's current value instead of jumping.
"""

import json
import os

import bpy
import numpy as np

from . import common, stagger

BUILTIN = {
    "Ease In-Out": {"anchored": True, "keys": [(0.0, 0.0), (1.0, 1.0)]},
    "Overshoot": {"anchored": True, "keys": [(0.0, 0.0), (0.7, 1.12), (1.0, 1.0)]},
    "Anticipation": {"anchored": True, "keys": [(0.0, 0.0), (0.25, -0.12), (1.0, 1.0)]},
    "Bounce Settle": {"anchored": True, "keys": [(0.0, 0.0), (0.45, 1.0), (0.62, 0.82), (0.78, 1.0),
                                                 (0.88, 0.94), (1.0, 1.0)]},
}
_enum_cache = []   # Blender needs the item strings kept alive
_clipboard = {"curves": [], "x0": 0.0, "x1": 0.0}


# --------------------------------------------------------------------------
# Shape library
# --------------------------------------------------------------------------

def library_path():
    try:
        if common.PKG.startswith("bl_ext."):
            folder = bpy.utils.extension_path_user(common.PKG, create=True)
        else:
            folder = bpy.utils.user_resource('CONFIG', path="maya_graph_editor", create=True)
    except Exception:
        folder = ""
    return os.path.join(folder, "shapes.json") if folder else ""


def load_user_shapes():
    path = library_path()
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return {}


def save_user_shapes(shapes):
    path = library_path()
    if not path:
        return False
    with open(path, "w", encoding="utf-8") as f:
        json.dump(shapes, f, indent=1)
    return True


def all_shapes():
    out = dict(BUILTIN)
    out.update(load_user_shapes())
    return out


def enum_items(_self=None, _context=None):
    _enum_cache[:] = [(name, name, "Built-in shape" if name in BUILTIN else "Your shape")
                      for name in all_shapes()]
    return _enum_cache


def shape_from_snapshot(snap):
    """Normalise the selected keys: time 0..1, value 0 at the first key and 1
    at the last (or by the value range if the shape ends where it starts)."""
    idx = np.flatnonzero(snap.selected)
    if len(idx) < 2:
        return None
    x, y = snap.co[idx, 0], snap.co[idx, 1]
    dur = x[-1] - x[0]
    if dur < 1e-9:
        return None
    anchored = abs(y[-1] - y[0]) > 1e-9
    vs = (y[-1] - y[0]) if anchored else (float(y.max() - y.min()) or 1.0)
    keys = []
    for j, i in enumerate(idx):
        keys.append({
            "u": float((x[j] - x[0]) / dur), "v": float((y[j] - y[0]) / vs),
            "hl": [float((snap.hl[i, 0] - x[j]) / dur), float((snap.hl[i, 1] - y[j]) / vs)],
            "hr": [float((snap.hr[i, 0] - x[j]) / dur), float((snap.hr[i, 1] - y[j]) / vs)],
            "lt": snap.enums["handle_left_type"][i], "rt": snap.enums["handle_right_type"][i],
            "ipo": snap.enums["interpolation"][i],
        })
    return {"anchored": bool(anchored), "keys": keys}


def shape_snapshot(shape, x0, x1, y0, y1, amplitude, extrapolation='CONSTANT'):
    """Keys of `shape` stretched from (x0, y0) to (x1, y1)."""
    dur = x1 - x0
    vs = (y1 - y0) if shape.get("anchored", True) else (amplitude if abs(amplitude) > 1e-9 else 1.0)
    keys = shape["keys"]
    simple = not isinstance(keys[0], dict)
    us = [k[0] if simple else k["u"] for k in keys]
    vv = [k[1] if simple else k["v"] for k in keys]
    snap = common.CurveSnapshot.build([x0 + u * dur for u in us], [y0 + v * vs for v in vv],
                                      extrapolation=extrapolation)
    if not simple:
        for j, k in enumerate(keys):
            snap.hl[j] = (snap.co[j, 0] + k["hl"][0] * dur, snap.co[j, 1] + k["hl"][1] * vs)
            snap.hr[j] = (snap.co[j, 0] + k["hr"][0] * dur, snap.co[j, 1] + k["hr"][1] * vs)
            snap.enums["handle_left_type"][j] = k["lt"]
            snap.enums["handle_right_type"][j] = k["rt"]
            snap.enums["interpolation"][j] = k["ipo"]
    return snap


def apply_shape(fc, shape):
    """Replace the selected key range of fc by the shape. True if applied."""
    cur = common.CurveSnapshot.of(fc)
    idx = np.flatnonzero(cur.selected)
    if len(idx) < 2:
        return False
    x0, y0 = cur.co[idx[0]]
    x1, y1 = cur.co[idx[-1]]
    if x1 - x0 < 1e-9:
        return False
    ys = cur.co[idx, 1]
    gen = shape_snapshot(shape, x0, x1, y0, y1, float(ys.max() - ys.min()), cur.extrapolation)
    for a in cur.bools:
        cur.bools[a] = [False] * cur.n
    cur.splice(gen, x0, x1).write(fc)
    return True


# --------------------------------------------------------------------------
# Copy / paste
# --------------------------------------------------------------------------

def copy_keys(fcurves):
    """Returns the number of curves copied."""
    items = []
    for fc in fcurves:
        snap = common.CurveSnapshot.of(fc)
        if snap.selected.any():
            items.append({"path": fc.data_path, "index": fc.array_index,
                          "prop": stagger.split_path(fc.data_path)[1],
                          "snap": snap.subset(snap.selected)})
    if items:
        xs = np.concatenate([it["snap"].co[:, 0] for it in items])
        _clipboard.update(curves=items, x0=float(xs.min()), x1=float(xs.max()))
    return len(items)


def clipboard_size():
    return len(_clipboard["curves"])


def _source_for(fc):
    items = _clipboard["curves"]
    for it in items:
        if it["path"] == fc.data_path and it["index"] == fc.array_index:
            return it["snap"]
    prop = stagger.split_path(fc.data_path)[1]
    for it in items:
        if it["prop"] == prop and it["index"] == fc.array_index:
            return it["snap"]
    return items[0]["snap"] if len(items) == 1 else None


def paste_curve(fc, src, mode, frame, relative=False):
    """Paste clipboard keys `src` into fc. Returns True if pasted."""
    cur = common.CurveSnapshot.of(fc)
    cx0, cx1 = _clipboard["x0"], _clipboard["x1"]
    length = cx1 - cx0
    scale, t0 = 1.0, float(frame)
    if mode == 'FIT':
        sel_x = cur.co[cur.selected, 0]
        if len(sel_x) < 2 or sel_x.max() - sel_x.min() < 1e-9 or length < 1e-9:
            return False
        t0 = float(sel_x.min())
        scale = float(sel_x.max() - sel_x.min()) / length
    t1 = t0 + length * scale
    x = src.co[:, 0]
    nx = t0 + (x - cx0) * scale
    dy = 0.0
    if relative and src.n:
        dy = fc.evaluate(float(nx[0])) - src.co[0, 1]
    co, hl, hr = src.co.copy(), src.hl.copy(), src.hr.copy()
    co[:, 0] = nx
    hl[:, 0] = nx + (src.hl[:, 0] - x) * scale
    hr[:, 0] = nx + (src.hr[:, 0] - x) * scale
    for a in (co, hl, hr):
        a[:, 1] += dy
    new = common.CurveSnapshot.from_arrays(src, co, hl, hr, range(src.n))
    for a in new.bools:
        new.bools[a] = [True] * new.n
    for a in cur.bools:
        cur.bools[a] = [False] * cur.n

    if mode == 'INSERT':
        later = cur.co[:, 0] >= t0 - 1e-6
        for arr in (cur.co, cur.hl, cur.hr):
            arr[later, 0] += length
        out = common.CurveSnapshot.concat([cur, new])
    elif mode == 'MERGE':
        clash = np.zeros(cur.n, dtype=bool)
        for f in nx:
            clash |= np.abs(cur.co[:, 0] - f) < 1e-3
        out = common.CurveSnapshot.concat([cur.subset(~clash), new])
    else:  # REPLACE, FIT
        out = cur.splice(new, t0, t1)
    out.extrapolation = cur.extrapolation
    out.write(fc)
    return True


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class _Op:
    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None


class MGE_OT_shape_save(_Op, bpy.types.Operator):
    bl_idname = "mge.shape_save"
    bl_label = "Save Shape"
    bl_description = "Save the shape of the selected keys (first curve with a selection) to the library"
    bl_options = {'REGISTER'}

    name: bpy.props.StringProperty(name="Name", default="My Shape")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.name.strip()
        if not name or name in BUILTIN:
            self.report({'WARNING'}, "Pick a name that isn't a built-in shape")
            return {'CANCELLED'}
        for fc in common.editable_fcurves(context):
            shape = shape_from_snapshot(common.CurveSnapshot.of(fc))
            if shape is not None:
                shapes = load_user_shapes()
                shapes[name] = shape
                if not save_user_shapes(shapes):
                    self.report({'ERROR'}, "Could not write the shape library")
                    return {'CANCELLED'}
                self.report({'INFO'}, "Saved shape '%s' (%d keys)" % (name, len(shape["keys"])))
                return {'FINISHED'}
        self.report({'WARNING'}, "Select at least two keys on a curve")
        return {'CANCELLED'}


class MGE_OT_shape_apply(_Op, bpy.types.Operator):
    bl_idname = "mge.shape_apply"
    bl_label = "Apply Shape"
    bl_description = ("Replace the selected keys of every curve with the chosen shape, stretched "
                      "between the first and last selected key")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        st = common.get_settings(context)
        shape = all_shapes().get(st.shape_active)
        if shape is None:
            self.report({'WARNING'}, "Pick a shape first")
            return {'CANCELLED'}
        n = sum(apply_shape(fc, shape) for fc in common.editable_fcurves(context))
        if not n:
            self.report({'WARNING'}, "Select at least two keys (the start and end of the move)")
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_OT_shape_delete(_Op, bpy.types.Operator):
    bl_idname = "mge.shape_delete"
    bl_label = "Delete Shape"
    bl_description = "Delete the chosen shape from your library (built-in shapes stay)"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        name = common.get_settings(context).shape_active
        shapes = load_user_shapes()
        if name not in shapes:
            self.report({'WARNING'}, "Built-in shapes can't be deleted")
            return {'CANCELLED'}
        del shapes[name]
        save_user_shapes(shapes)
        return {'FINISHED'}


class MGE_OT_copy_keys(_Op, bpy.types.Operator):
    bl_idname = "mge.copy_keys"
    bl_label = "Copy Keys"
    bl_description = "Copy the selected keys for Paste below"
    bl_options = {'REGISTER'}

    def execute(self, context):
        n = copy_keys(common.editable_fcurves(context))
        if not n:
            self.report({'WARNING'}, "No keyframes selected")
            return {'CANCELLED'}
        self.report({'INFO'}, "Copied keys from %d curve(s)" % n)
        return {'FINISHED'}


class MGE_OT_paste_keys(_Op, bpy.types.Operator):
    bl_idname = "mge.paste_keys"
    bl_label = "Paste Keys"
    bl_description = "Paste the copied keys"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(items=(
        ('MERGE', "Merge", "Paste at the playhead, keeping the existing keys"),
        ('REPLACE', "Replace", "Paste at the playhead, removing existing keys in that time range"),
        ('INSERT', "Insert", "Paste at the playhead, pushing later keys back to make room"),
        ('FIT', "Fit", "Stretch the copied keys to fill the selected keys' time range"),
    ))

    @classmethod
    def description(cls, context, properties):
        return cls.bl_rna.properties["mode"].enum_items[properties.mode].description

    def execute(self, context):
        if not clipboard_size():
            self.report({'WARNING'}, "Copy some keys first")
            return {'CANCELLED'}
        st = common.get_settings(context)
        curves = common.editable_fcurves(context)
        picked = [fc for fc in curves if fc.select or
                  any(k.select_control_point for k in fc.keyframe_points)] or curves
        frame = float(context.scene.frame_current)
        n = 0
        for fc in picked:
            src = _source_for(fc)
            if src is not None:
                n += paste_curve(fc, src, self.mode, frame, st.paste_relative)
        if not n:
            self.report({'WARNING'}, "Nothing pasted: no matching channels"
                        + (" or no keys selected to fit to" if self.mode == 'FIT' else ""))
            return {'CANCELLED'}
        common.redraw_graph_editors()
        return {'FINISHED'}


class MGE_PT_shapes(bpy.types.Panel):
    bl_label = "Shapes & Paste"
    bl_idname = "MGE_PT_shapes"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 15
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        box = layout.box()
        box.label(text="Shape Library")
        row = box.row(align=True)
        row.prop(st, "shape_active", text="")
        row.operator("mge.shape_save", text="", icon='ADD')
        row.operator("mge.shape_delete", text="", icon='X')
        box.operator("mge.shape_apply", icon='IPO_BACK')

        box = layout.box()
        row = box.row()
        row.label(text="Copy / Paste Keys")
        n = clipboard_size()
        box.operator("mge.copy_keys", icon='COPYDOWN',
                     text="Copy Keys (%d)" % n if n else "Copy Keys")
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        for mode in ('MERGE', 'REPLACE', 'INSERT', 'FIT'):
            grid.operator("mge.paste_keys", text=mode.title()).mode = mode
        box.prop(st, "paste_relative")


classes = (MGE_OT_shape_save, MGE_OT_shape_apply, MGE_OT_shape_delete,
           MGE_OT_copy_keys, MGE_OT_paste_keys, MGE_PT_shapes)


def register_tool():
    pass


def unregister_tool():
    pass
