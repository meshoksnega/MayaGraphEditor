"""Tool 3 - Curve Simplify with live preview.

Select a run of keyframes, press "Simplify", then move the mouse (or drag the
slider in the sidebar) to change the tolerance.  The real curves are rebuilt
live from a snapshot, so the preview is exactly what Blender will play back.
Nothing is permanent until you confirm: Esc / right click restores the
snapshot byte for byte.

Tolerance is a percentage of each curve's value range over the selected keys,
so one slider behaves sensibly for location, rotation and scale channels at
the same time.
"""

import bpy
import numpy as np

from . import common, simplify_core

MAX_PCT = 25.0          # slider range shown in the HUD
_session = None
_last_result = None


SYNC_KEYS = 300          # smaller selections are analysed immediately
TICK_BUDGET = 0.04       # seconds of analysis per modal timer tick


class CurvePlan:
    __slots__ = ("key", "snap", "order", "cum", "span", "applied", "planner", "removable")


class Session:
    def __init__(self, area, plans):
        self.area_ptr = area.as_pointer()
        self.plans = plans
        self.handle = None
        self.last_mouse_x = None
        self.cursor_window = None
        self.timer = None
        self.pending = [p for p in plans if p.order is None]  # still being analysed
        self.iter = None
        self.progress = 0.0

    @property
    def planning(self):
        return bool(self.pending)

    def step(self, budget=TICK_BUDGET):
        """Advance the analysis for up to `budget` seconds. True when finished."""
        import time
        end = time.perf_counter() + budget
        total = max(sum(int(p.removable) for p in self.plans), 1)
        while self.pending and time.perf_counter() < end:
            plan = self.pending[0]
            if self.iter is None:
                self.iter = plan.planner.plan_iter()
            try:
                frac = next(self.iter)
            except StopIteration:
                frac = 1.0
            if frac >= 1.0 and getattr(plan.planner, "result", None) is not None:
                plan.order, plan.cum = plan.planner.result
                plan.planner = None
                self.pending.pop(0)
                self.iter = None
            done = sum(int(p.removable) for p in self.plans if p.order is not None)
            cur = int(plan.removable) * (frac if plan.order is None else 0.0)
            self.progress = (done + cur) / total
        return not self.pending


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------

def _runs(selected):
    idx = np.flatnonzero(selected)
    if len(idx) == 0:
        return []
    return np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)


def build_curve_plan(fc, analyse=True):
    """CurvePlan for one F-Curve, or None if fewer than 3 consecutive keys
    are selected.  First and last key of every selected run are kept.
    With analyse=False the removal order is left to plan.planner."""
    snap = common.CurveSnapshot.of(fc)
    removable = np.zeros(snap.n, dtype=bool)
    for run in _runs(snap.selected):
        if len(run) >= 3:
            removable[run[1:-1]] = True
    if not removable.any():
        return None
    x_lo, x_hi = snap.co[0, 0], snap.co[-1, 0]
    step = max(0.5, (x_hi - x_lo) / 4000.0)
    xs = np.unique(np.concatenate([np.arange(x_lo, x_hi, step), snap.co[:, 0]]))
    ys = np.array([fc.evaluate(float(x)) for x in xs])
    sel_x = snap.co[snap.selected, 0]
    in_sel = (xs >= sel_x.min()) & (xs <= sel_x.max())
    span = float(ys[in_sel].max() - ys[in_sel].min())
    planner = simplify_core.make_planner(
        snap.co, snap.hl, snap.hr,
        snap.enums["handle_left_type"], snap.enums["handle_right_type"],
        snap.enums["interpolation"], removable, xs, ys,
        flat_ends=(snap.extrapolation == 'CONSTANT'),
        smoothing=getattr(fc, "auto_smoothing", 'NONE'))
    plan = CurvePlan()
    plan.key, plan.snap = common.curve_key(fc), snap
    plan.span, plan.applied, plan.removable = span, 0, int(removable.sum())
    plan.order = plan.cum = None
    plan.planner = planner
    if analyse:
        plan.order, plan.cum = planner.plan()
        plan.planner = None
    return plan


def build_plans(context, analyse=True):
    plans = []
    for fc in common.editable_fcurves(context):
        plan = build_curve_plan(fc, analyse)
        if plan is not None:
            plans.append(plan)
    return plans


def counts(plans, pct):
    """(keys before, keys after) over the planned curves at `pct` tolerance."""
    before = sum(p.snap.n for p in plans)
    removed = sum(simplify_core.removal_count(p.cum, p.span * pct / 100.0)
                  for p in plans if p.cum is not None)
    return before, before - removed


# --------------------------------------------------------------------------
# Applying a tolerance (the live preview)
# --------------------------------------------------------------------------

def apply_tolerance(context, pct):
    ses = _session
    if ses is None or ses.planning:
        return
    fmap = common.fcurve_map(context)
    for p in ses.plans:
        fc = fmap.get(p.key)
        if fc is None:
            continue
        cnt = simplify_core.removal_count(p.cum, p.span * pct / 100.0)
        if cnt == p.applied:
            continue
        keep = np.setdiff1d(np.arange(p.snap.n), p.order[:cnt])
        p.snap.write(fc, keep=keep)
        p.applied = cnt
    common.redraw_graph_editors()


def on_tolerance_changed(context):
    """Called by the scene property so the sidebar slider drives the preview."""
    if _session is not None:
        try:
            apply_tolerance(context, common.get_settings(context).simplify_tolerance)
        except Exception:
            common.log_exception("simplify preview")


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
    common.modal_release("simplify")
    _session = None


def finish(context, apply):
    """End the session. apply=False restores every curve to its snapshot."""
    global _session, _last_result
    ses = _session
    if ses is None:
        return
    if not apply:
        fmap = common.fcurve_map(context)
        for p in ses.plans:
            fc = fmap.get(p.key)
            if fc is not None:
                p.snap.write(fc)
    if ses.handle is not None:
        bpy.types.SpaceGraphEditor.draw_handler_remove(ses.handle, 'WINDOW')
    if ses.timer is not None:
        try:
            context.window_manager.event_timer_remove(ses.timer)
        except Exception:
            pass
    try:
        context.workspace.status_text_set(None)
    except Exception:
        pass
    try:
        (ses.cursor_window or context.window).cursor_set('DEFAULT')
    except Exception:
        pass
    common.modal_release("simplify")
    _session = None
    _last_result = 'APPLY' if apply else 'CANCEL'
    common.redraw_graph_editors()


# --------------------------------------------------------------------------
# HUD
# --------------------------------------------------------------------------

def _draw_hud():
    ses = _session
    ctx = bpy.context
    if ses is None or ctx.area is None or ctx.area.as_pointer() != ses.area_ptr:
        return
    region = ctx.region
    if region is None or region.type != 'WINDOW':
        return
    try:
        pct = ctx.scene.mge_settings.simplify_tolerance
        if ses.planning:
            n = sum(p.snap.n for p in ses.plans)
            common.draw_slider_hud(
                region, "SIMPLIFY   analysing %d keys... %d%%" % (n, int(ses.progress * 100)),
                ses.progress, "Esc = cancel (nothing has changed yet)")
            return
        before, after = counts(ses.plans, pct)
        common.draw_slider_hud(
            region, "SIMPLIFY   tolerance %.2f%%   keys %d \u2192 %d  (\u2212%d)"
            % (pct, before, after, before - after), pct / MAX_PCT,
            "move mouse / drag slider \u00b7 Shift = fine \u00b7 click or Enter = apply \u00b7 "
            "Esc or right-click = cancel")
    except Exception:
        common.log_exception("simplify HUD")


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class MGE_OT_simplify(bpy.types.Operator):
    bl_idname = "mge.simplify"
    bl_label = "Simplify Selected Keys"
    bl_description = ("Reduce the number of selected keyframes with a live preview. "
                      "Nothing is removed until you confirm")
    bl_options = {'UNDO', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None

    def invoke(self, context, event):
        global _session
        plans = build_plans(context, analyse=False)
        if not plans:
            self.report({'WARNING'}, "Select at least 3 consecutive keyframes on a curve")
            return {'CANCELLED'}
        if not common.modal_claim("simplify"):
            return {'CANCELLED'}
        if sum(p.snap.n for p in plans) <= SYNC_KEYS:
            for p in plans:
                p.order, p.cum = p.planner.plan()
                p.planner = None
        ses = Session(context.area, plans)
        ses.handle = bpy.types.SpaceGraphEditor.draw_handler_add(
            _draw_hud, (), 'WINDOW', 'POST_PIXEL')
        ses.last_mouse_x = event.mouse_x
        ses.cursor_window = context.window
        _session = ses
        try:
            context.window.cursor_set('MOVE_X')
        except Exception:
            pass
        context.workspace.status_text_set(
            "Simplify: move mouse = tolerance (Shift: fine)   Click/Enter: apply   Esc/RMB: cancel")
        if ses.planning:
            ses.timer = context.window_manager.event_timer_add(0.01, window=context.window)
        else:
            apply_tolerance(context, common.get_settings(context).simplify_tolerance)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if _session is None:  # finished from the sidebar buttons
            return {'FINISHED'} if _last_result == 'APPLY' else {'CANCELLED'}
        try:
            return self._modal(context, event)
        except Exception:
            common.log_exception("simplify modal")
            finish(context, apply=False)
            return {'CANCELLED'}

    def _modal(self, context, event):
        ses = _session
        if not common.tool_enabled("simplify") or context.area is None:
            finish(context, apply=False)
            return {'CANCELLED'}
        region = common.window_region(context.area)
        inside = region is not None and common.event_in_region(region, event)

        if ses.planning:
            if event.type == 'TIMER':
                if ses.step():
                    context.window_manager.event_timer_remove(ses.timer)
                    ses.timer = None
                    apply_tolerance(context, common.get_settings(context).simplify_tolerance)
                common.redraw_graph_editors()
                return {'RUNNING_MODAL'}
            if event.value == 'PRESS' and (event.type == 'ESC' or
                                           (event.type == 'RIGHTMOUSE' and inside)):
                finish(context, apply=False)
                return {'CANCELLED'}
            if common.is_navigation_event(event) or not inside:
                return {'PASS_THROUGH'}
            return {'RUNNING_MODAL'}

        if event.value == 'PRESS':
            if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and inside):
                finish(context, apply=False)
                return {'CANCELLED'}
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} or (
                    event.type == 'LEFTMOUSE' and inside):
                finish(context, apply=True)
                return {'FINISHED'}
        if not inside:
            ses.last_mouse_x = None
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            if ses.last_mouse_x is not None:
                dx = event.mouse_x - ses.last_mouse_x
                st = common.get_settings(context)
                scale = MAX_PCT / max(region.width * 0.5, 1.0)
                if event.shift:
                    scale *= 0.1
                new = min(max(st.simplify_tolerance + dx * scale, 0.0), 100.0)
                if new != st.simplify_tolerance:
                    st.simplify_tolerance = new  # update callback applies it
            ses.last_mouse_x = event.mouse_x
            return {'RUNNING_MODAL'}
        if common.is_navigation_event(event):
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class MGE_OT_simplify_confirm(bpy.types.Operator):
    bl_idname = "mge.simplify_confirm"
    bl_label = "Apply"
    bl_description = "Keep the simplified curves"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return is_active()

    def execute(self, context):
        finish(context, apply=True)
        return {'FINISHED'}


class MGE_OT_simplify_cancel(bpy.types.Operator):
    bl_idname = "mge.simplify_cancel"
    bl_label = "Cancel"
    bl_description = "Restore the curves exactly as they were"
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

class MGE_PT_simplify(bpy.types.Panel):
    bl_label = "Simplify"
    bl_idname = "MGE_PT_simplify"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 3

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        layout.prop(st, "simplify_tolerance", slider=True)
        if is_active() and _session.planning:
            layout.label(text="Analysing... %d%%" % int(_session.progress * 100))
            layout.operator("mge.simplify_cancel", icon='X')
        elif is_active():
            before, after = counts(_session.plans, st.simplify_tolerance)
            layout.label(text="Keys: %d → %d  (−%d)" % (before, after, before - after))
            row = layout.row(align=True)
            row.scale_y = 1.3
            row.operator("mge.simplify_confirm", icon='CHECKMARK')
            row.operator("mge.simplify_cancel", icon='X')
        else:
            row = layout.row()
            row.scale_y = 1.3
            row.operator("mge.simplify", icon='FCURVE')
            col = layout.column(align=True)
            col.label(text="Select 3+ consecutive keys.")
            col.label(text="Ends of each run are kept.")


classes = (MGE_OT_simplify, MGE_OT_simplify_confirm, MGE_OT_simplify_cancel,
           MGE_PT_simplify)


def register_tool():
    pass


def unregister_tool():
    if _session is not None:
        try:
            finish(bpy.context, apply=False)
        except Exception:
            common.log_exception("simplify unregister")
