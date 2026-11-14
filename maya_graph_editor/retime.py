"""Tool 4 - Retiming / lattice tool.

Press "Retime Selection": a lattice (two vertical edges with grips) appears
around the selected keyframes of *all* curves.  Drag an edge to stretch or
compress the whole range in time - every selected key (and its handle
x-lengths) is scaled about the opposite edge, so relative spacing and curve
shape are preserved.  Later keys can ripple along so nothing collides.
Enter / button = apply, Esc / right-click = cancel.
"""

import bpy
import numpy as np

from . import common

GRAB_PX = 10        # how close to an edge (pixels) counts as grabbing it
_session = None
_last_result = None


# --------------------------------------------------------------------------
# Maths (no UI)
# --------------------------------------------------------------------------

def retime_curve(snap, t0, t1, new_t0, new_t1, ripple):
    """Map selected keys of `snap` from [t0, t1] to [new_t0, new_t1].

    Returns (co, hl, hr) arrays.  Handle x-lengths of retimed keys are scaled
    by the same factor so the shape is only stretched, never distorted.
    Unselected keys before/after the range move with the edge when `ripple`.
    """
    x = snap.co[:, 0]
    sel = snap.selected
    scale = (new_t1 - new_t0) / (t1 - t0)
    nx = x.copy()
    nx[sel] = new_t0 + (x[sel] - t0) * scale
    if ripple:
        nx[(~sel) & (x > t1)] += new_t1 - t1
        nx[(~sel) & (x < t0)] += new_t0 - t0
    ratio = np.where(sel, scale, 1.0)
    co, hl, hr = snap.co.copy(), snap.hl.copy(), snap.hr.copy()
    co[:, 0] = nx
    hl[:, 0] = nx + (snap.hl[:, 0] - x) * ratio
    hr[:, 0] = nx + (snap.hr[:, 0] - x) * ratio
    return co, hl, hr


def selection_range(snaps):
    xs = [s.co[s.selected, 0] for s in snaps if s.selected.any()]
    if not xs:
        return None
    allx = np.concatenate(xs)
    return float(allx.min()), float(allx.max())


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------

class CurveState:
    __slots__ = ("key", "orig", "base")


class Session:
    def __init__(self, area):
        self.area_ptr = area.as_pointer()
        self.curves = []
        self.t0 = self.t1 = 0.0          # committed range
        self.cur_t0 = self.cur_t1 = 0.0  # live range
        self.drag = None                 # None | 'L' | 'R'
        self.grab_off = 0.0
        self.hover = None
        self.handle = None
        self.cursor_window = None


def _begin(context):
    ses = Session(context.area)
    for fc in common.editable_fcurves(context):
        snap = common.CurveSnapshot.of(fc)
        if snap.selected.any():
            cs = CurveState()
            cs.key, cs.orig, cs.base = common.curve_key(fc), snap, snap.copy()
            ses.curves.append(cs)
    rng = selection_range([c.base for c in ses.curves])
    if rng is None or rng[1] - rng[0] < 1e-4:
        return None
    ses.t0 = ses.cur_t0 = rng[0]
    ses.t1 = ses.cur_t1 = rng[1]
    return ses


def _apply_range(context, new_t0, new_t1):
    ses = _session
    ripple = common.get_settings(context).retime_ripple
    fmap = common.fcurve_map(context)
    for c in ses.curves:
        fc = fmap.get(c.key)
        if fc is None:
            continue
        co, hl, hr = retime_curve(c.base, ses.t0, ses.t1, new_t0, new_t1, ripple)
        c.base.write(fc, co=co, hl=hl, hr=hr)
    ses.cur_t0, ses.cur_t1 = new_t0, new_t1
    common.redraw_graph_editors()


def _commit(context):
    """Make the current state the new base for the next drag."""
    ses = _session
    fmap = common.fcurve_map(context)
    for c in ses.curves:
        fc = fmap.get(c.key)
        if fc is not None:
            c.base = common.CurveSnapshot.of(fc)
    ses.t0, ses.t1 = ses.cur_t0, ses.cur_t1
    ses.drag = None


def _restore_base(context):
    ses = _session
    fmap = common.fcurve_map(context)
    for c in ses.curves:
        fc = fmap.get(c.key)
        if fc is not None:
            c.base.write(fc)
    ses.cur_t0, ses.cur_t1 = ses.t0, ses.t1
    ses.drag = None


def is_active():
    return _session is not None


def abort_session():
    """Drop a session without touching any data (e.g. a new file is loading)."""
    global _session
    ses = _session
    if ses is None:
        return
    if ses.handle is not None:
        try:
            bpy.types.SpaceGraphEditor.draw_handler_remove(ses.handle, 'WINDOW')
        except Exception:
            pass
    common.modal_release("retime")
    _session = None


def finish(context, apply):
    global _session, _last_result
    ses = _session
    if ses is None:
        return
    if apply:
        if ses.drag is not None:
            _commit(context)
    else:
        fmap = common.fcurve_map(context)
        for c in ses.curves:
            fc = fmap.get(c.key)
            if fc is not None:
                c.orig.write(fc)
    if ses.handle is not None:
        bpy.types.SpaceGraphEditor.draw_handler_remove(ses.handle, 'WINDOW')
    try:
        context.workspace.status_text_set(None)
    except Exception:
        pass
    try:
        (ses.cursor_window or context.window).cursor_set('DEFAULT')
    except Exception:
        pass
    common.modal_release("retime")
    _session = None
    _last_result = 'APPLY' if apply else 'CANCEL'
    common.redraw_graph_editors()


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def _frame_to_px(region, tscale, frame):
    ox, _oy, sx, _sy = common.view_affine(region)
    return ox + frame * tscale * sx


def _draw_lattice():
    ses = _session
    ctx = bpy.context
    if ses is None or ctx.area is None or ctx.area.as_pointer() != ses.area_ptr:
        return
    region, space, scene = ctx.region, ctx.space_data, ctx.scene
    if region is None or region.type != 'WINDOW':
        return
    try:
        tscale = common.time_scale(space, scene)
        h = region.height
        xl = _frame_to_px(region, tscale, ses.cur_t0)
        xr = _frame_to_px(region, tscale, ses.cur_t1)
        common.draw_rect(xl, 0, xr, h, (0.35, 0.65, 1.0, 0.10))
        for edge, x in (('L', xl), ('R', xr)):
            active = ses.drag == edge or (ses.drag is None and ses.hover == edge)
            col = (1.0, 0.8, 0.2, 1.0) if active else (0.35, 0.65, 1.0, 1.0)
            common.draw_polyline([(x, 0), (x, h)], col, 2.0 if active else 1.5)
            common.draw_rect(x - 6, h / 2 - 22, x + 6, h / 2 + 22, col)
            common.draw_rect(x - 1, h / 2 - 12, x + 1, h / 2 + 12, (0.1, 0.1, 0.12, 1))
        width0, width1 = ses.t1 - ses.t0, ses.cur_t1 - ses.cur_t0
        pct = 100.0 * width1 / width0 if width0 else 100.0
        label = "RETIME   %.1f → %.1f   (length %.1f → %.1f,  %.0f%%)" % (
            ses.cur_t0, ses.cur_t1, width0, width1, pct)
        common.draw_text(max(xl, 12) + 8, h - 24, label, 14, (1, 1, 1, 1))
        common.draw_text(12, 10, "drag an edge to stretch / compress · Ctrl = snap to "
                         "frames · Enter = apply · Esc = cancel", 11,
                         (0.75, 0.75, 0.78, 1))
    except Exception:
        common.log_exception("retime draw")


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class MGE_OT_retime(bpy.types.Operator):
    bl_idname = "mge.retime"
    bl_label = "Retime Selection"
    bl_description = ("Show a draggable lattice around the selected keyframes "
                      "(across all curves) to stretch or compress them in time")
    bl_options = {'UNDO', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None

    def invoke(self, context, event):
        global _session
        ses = _begin(context)
        if ses is None:
            self.report({'WARNING'}, "Select keyframes spanning at least two different frames")
            return {'CANCELLED'}
        if not common.modal_claim("retime"):
            return {'CANCELLED'}
        ses.handle = bpy.types.SpaceGraphEditor.draw_handler_add(
            _draw_lattice, (), 'WINDOW', 'POST_PIXEL')
        ses.cursor_window = context.window
        _session = ses
        context.workspace.status_text_set(
            "Retime: drag an edge   Ctrl: snap to frames   Enter: apply   Esc/RMB: cancel")
        context.window_manager.modal_handler_add(self)
        common.redraw_graph_editors()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if _session is None:  # finished from the sidebar buttons
            return {'FINISHED'} if _last_result == 'APPLY' else {'CANCELLED'}
        try:
            return self._modal(context, event)
        except Exception:
            common.log_exception("retime modal")
            finish(context, apply=False)
            return {'CANCELLED'}

    def _mouse_frame(self, context, region, event):
        scene, space = context.scene, context.space_data
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        vx = region.view2d.region_to_view(mx, my)[0]
        return vx / common.time_scale(space, scene), mx

    def _modal(self, context, event):
        ses = _session
        if not common.tool_enabled("retime") or context.area is None:
            finish(context, apply=False)
            return {'CANCELLED'}
        region = common.window_region(context.area)
        if region is None:
            return {'PASS_THROUGH'}
        inside = common.event_in_region(region, event)
        dragging = ses.drag is not None

        if event.value == 'PRESS':
            if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and (inside or dragging)):
                if dragging:
                    _restore_base(context)
                    return {'RUNNING_MODAL'}
                finish(context, apply=False)
                return {'CANCELLED'}
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
                finish(context, apply=True)
                return {'FINISHED'}

        if not (inside or dragging):
            ses.hover = None
            return {'PASS_THROUGH'}

        frame, mx = self._mouse_frame(context, region, event)
        tscale = common.time_scale(context.space_data, context.scene)

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and not dragging:
            if ses.hover:
                ses.drag = ses.hover
                edge = ses.t1 if ses.drag == 'R' else ses.t0
                ses.grab_off = frame - edge
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and dragging:
            _commit(context)
            return {'RUNNING_MODAL'}

        if event.type == 'MOUSEMOVE':
            if dragging:
                st = common.get_settings(context)
                min_len = max((ses.t1 - ses.t0) * 0.02, 0.01)
                target = frame - ses.grab_off
                if event.ctrl or st.retime_snap:
                    target = round(target)
                if ses.drag == 'R':
                    _apply_range(context, ses.t0, max(target, ses.t0 + min_len))
                else:
                    _apply_range(context, min(target, ses.t1 - min_len), ses.t1)
            else:
                dl = abs(mx - _frame_to_px(region, tscale, ses.cur_t0))
                dr = abs(mx - _frame_to_px(region, tscale, ses.cur_t1))
                hover = None
                if min(dl, dr) <= GRAB_PX:
                    hover = 'L' if dl < dr else 'R'
                if hover != ses.hover:
                    ses.hover = hover
                    common.redraw_graph_editors()
                try:
                    context.window.cursor_set('MOVE_X' if hover else 'DEFAULT')
                except Exception:
                    pass
            return {'RUNNING_MODAL'}

        if common.is_navigation_event(event):
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class MGE_OT_retime_confirm(bpy.types.Operator):
    bl_idname = "mge.retime_confirm"
    bl_label = "Apply"
    bl_description = "Keep the retimed keyframes"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return is_active()

    def execute(self, context):
        finish(context, apply=True)
        return {'FINISHED'}


class MGE_OT_retime_cancel(bpy.types.Operator):
    bl_idname = "mge.retime_cancel"
    bl_label = "Cancel"
    bl_description = "Put every key back where it was"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return is_active()

    def execute(self, context):
        finish(context, apply=False)
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------

class MGE_PT_retime(bpy.types.Panel):
    bl_label = "Retime"
    bl_idname = "MGE_PT_retime"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 4

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        col = layout.column(align=True)
        col.prop(st, "retime_ripple")
        col.prop(st, "retime_snap")
        if is_active():
            ses = _session
            w0, w1 = ses.t1 - ses.t0, ses.cur_t1 - ses.cur_t0
            layout.label(text="%.1f → %.1f frames (%.0f%%)" % (
                w0, w1, 100.0 * w1 / w0 if w0 else 100.0))
            row = layout.row(align=True)
            row.scale_y = 1.3
            row.operator("mge.retime_confirm", icon='CHECKMARK')
            row.operator("mge.retime_cancel", icon='X')
        else:
            row = layout.row()
            row.scale_y = 1.3
            row.operator("mge.retime", icon='ARROW_LEFTRIGHT')
            layout.label(text="Select keys on one or more curves.")


classes = (MGE_OT_retime, MGE_OT_retime_confirm, MGE_OT_retime_cancel, MGE_PT_retime)


def register_tool():
    pass


def unregister_tool():
    if _session is not None:
        try:
            finish(bpy.context, apply=False)
        except Exception:
            common.log_exception("retime unregister")
