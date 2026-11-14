"""Shared live-preview slider tool (used by Tween, Smooth and Time Warp).

A tool subclasses SliderTool and only says how keys move for a value:
    prepare(context) -> [Job] or an error string
    compute(job, value) -> (co, hl, hr) arrays for that curve

The framework does the rest, like Simplify: drag the mouse (Shift = fine,
Ctrl = snap) or the sidebar slider, the real curves update live from a
snapshot, Click/Enter keeps it as one undo step, Esc/right-click restores
the snapshot exactly.
"""

import bpy

from . import common

_session = None
_last_result = None


class Job:
    """One F-Curve being edited: identity, snapshot and tool data."""
    __slots__ = ("key", "snap", "data")

    def __init__(self, key, snap, data=None):
        self.key, self.snap, self.data = key, snap, data


class SliderTool:
    id = ""            # operator: mge.<id>
    label = ""         # HUD title
    op_label = ""
    description = ""
    setting = ""       # MGE_Settings float property driving the value
    vmin, vmax = 0.0, 100.0
    snap_step = 10.0
    hint = ""

    write = None       # optional: write(job, fc, value) instead of compute()

    def prepare(self, context):
        raise NotImplementedError

    def compute(self, job, value):
        raise NotImplementedError

    def describe(self, value):
        return "%.1f" % value


class Session:
    def __init__(self, tool, area, jobs):
        self.tool = tool
        self.area_ptr = area.as_pointer()
        self.jobs = jobs
        self.handle = None
        self.last_mouse_x = None
        self.cursor_window = None
        self.raw = 0.0


def active_tool_id():
    return _session.tool.id if _session else None


def selected_jobs(context, need=1):
    """Jobs for editable curves with at least `need` selected keys."""
    jobs = []
    for fc in common.editable_fcurves(context):
        snap = common.CurveSnapshot.of(fc)
        if snap.selected.sum() >= need:
            jobs.append(Job(common.curve_key(fc), snap))
    return jobs


def apply_value(context, value):
    ses = _session
    if ses is None:
        return
    fmap = common.fcurve_map(context)
    for job in ses.jobs:
        fc = fmap.get(job.key)
        if fc is None:
            continue
        if ses.tool.write is not None:
            ses.tool.write(job, fc, value)  # tools that add / remove keys
        else:
            co, hl, hr = ses.tool.compute(job, value)
            job.snap.write(fc, co=co, hl=hl, hr=hr)
    common.redraw_graph_editors()


def on_value_changed(tool_id, context):
    """Property update callback: the sidebar slider drives the preview."""
    if _session is not None and _session.tool.id == tool_id:
        try:
            apply_value(context, getattr(common.get_settings(context), _session.tool.setting))
        except Exception:
            common.log_exception("%s preview" % tool_id)


def finish(context, apply):
    global _session, _last_result
    ses = _session
    if ses is None:
        return
    fmap = common.fcurve_map(context)
    if not apply:
        for job in ses.jobs:
            fc = fmap.get(job.key)
            if fc is not None:
                job.snap.write(fc)
    elif ses.tool.id in ("warp", "stagger", "overlap"):
        from . import blocking
        blocking.auto_round(context, [fmap[j.key] for j in ses.jobs if j.key in fmap])
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
    common.modal_release("slider")
    _session = None
    _last_result = 'APPLY' if apply else 'CANCEL'
    common.redraw_graph_editors()


def abort_session():
    """Drop a session without touching data (a new file is loading)."""
    global _session
    if _session is None:
        return
    if _session.handle is not None:
        try:
            bpy.types.SpaceGraphEditor.draw_handler_remove(_session.handle, 'WINDOW')
        except Exception:
            pass
    common.modal_release("slider")
    _session = None


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
        tool = ses.tool
        value = getattr(ctx.scene.mge_settings, tool.setting)
        common.draw_slider_hud(region, "%s   %s" % (tool.label, tool.describe(value)),
                               (value - tool.vmin) / (tool.vmax - tool.vmin),
                               "move mouse / drag slider · Shift = fine · Ctrl = snap · "
                               "click or Enter = apply · Esc or right-click = cancel",
                               marks=tool_marks(tool))
    except Exception:
        common.log_exception("%s HUD" % ses.tool.id)


def tool_marks(tool):
    """Fractions along the bar to mark (e.g. 0% and 100% for Tween)."""
    marks = getattr(tool, "marks", ())
    return [(m - tool.vmin) / (tool.vmax - tool.vmin) for m in marks]


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

def make_operator(tool):
    """Build the modal operator class for a SliderTool instance."""

    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None

    def invoke(self, context, event):
        global _session
        jobs = tool.prepare(context)
        if isinstance(jobs, str):
            self.report({'WARNING'}, jobs)
            return {'CANCELLED'}
        if not jobs:
            self.report({'WARNING'}, "Select keyframes first")
            return {'CANCELLED'}
        if not common.modal_claim("slider"):
            return {'CANCELLED'}
        ses = Session(tool, context.area, jobs)
        ses.handle = bpy.types.SpaceGraphEditor.draw_handler_add(
            _draw_hud, (), 'WINDOW', 'POST_PIXEL')
        ses.last_mouse_x = event.mouse_x
        ses.cursor_window = context.window
        ses.raw = getattr(common.get_settings(context), tool.setting)
        _session = ses
        try:
            context.window.cursor_set('MOVE_X')
        except Exception:
            pass
        context.workspace.status_text_set(
            "%s: move mouse (Shift: fine, Ctrl: snap)   Click/Enter: apply   Esc/RMB: cancel"
            % tool.op_label)
        apply_value(context, getattr(common.get_settings(context), tool.setting))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if _session is None:  # finished from the sidebar buttons
            return {'FINISHED'} if _last_result == 'APPLY' else {'CANCELLED'}
        try:
            return _modal(self, context, event)
        except Exception:
            common.log_exception("%s modal" % tool.id)
            finish(context, apply=False)
            return {'CANCELLED'}

    def _modal(self, context, event):
        ses = _session
        if not common.tool_enabled(tool.id) or context.area is None:
            finish(context, apply=False)
            return {'CANCELLED'}
        region = common.window_region(context.area)
        inside = region is not None and common.event_in_region(region, event)
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
                st = common.get_settings(context)
                scale = (tool.vmax - tool.vmin) / max(region.width * 0.5, 1.0)
                if event.shift:
                    scale *= 0.1
                # ses.raw follows the mouse unsnapped; Ctrl only rounds what's applied
                ses.raw = min(max(ses.raw + (event.mouse_x - ses.last_mouse_x) * scale,
                                  tool.vmin), tool.vmax)
                new = round(ses.raw / tool.snap_step) * tool.snap_step if event.ctrl else ses.raw
                if new != getattr(st, tool.setting):
                    setattr(st, tool.setting, new)  # update callback applies it
            ses.last_mouse_x = event.mouse_x
            return {'RUNNING_MODAL'}
        if common.is_navigation_event(event):
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    cls = type("MGE_OT_" + tool.id, (bpy.types.Operator,), {
        "bl_idname": "mge." + tool.id,
        "bl_label": tool.op_label,
        "bl_description": tool.description,
        "bl_options": {'UNDO', 'BLOCKING'},
        "poll": classmethod(poll),
        "invoke": invoke,
        "modal": modal,
    })
    return cls


class MGE_OT_slider_confirm(bpy.types.Operator):
    bl_idname = "mge.slider_confirm"
    bl_label = "Apply"
    bl_description = "Keep the previewed result"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return _session is not None

    def execute(self, context):
        finish(context, apply=True)
        return {'FINISHED'}


class MGE_OT_slider_cancel(bpy.types.Operator):
    bl_idname = "mge.slider_cancel"
    bl_label = "Cancel"
    bl_description = "Restore the curves exactly as they were"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return _session is not None

    def execute(self, context):
        finish(context, apply=False)
        return {'FINISHED'}


def draw_panel(layout, context, tool, button_icon):
    """Standard panel body: slider, then Start or Apply/Cancel."""
    st = common.get_settings(context)
    layout.prop(st, tool.setting, slider=True)
    if _session is not None and _session.tool.id == tool.id:
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("mge.slider_confirm", icon='CHECKMARK')
        row.operator("mge.slider_cancel", icon='X')
    else:
        row = layout.row()
        row.scale_y = 1.3
        row.operator("mge." + tool.id, icon=button_icon)


core_classes = (MGE_OT_slider_confirm, MGE_OT_slider_cancel)


def unregister_tool_session(tool_id):
    if _session is not None and _session.tool.id == tool_id:
        try:
            finish(bpy.context, apply=False)
        except Exception:
            common.log_exception("%s unregister" % tool_id)
