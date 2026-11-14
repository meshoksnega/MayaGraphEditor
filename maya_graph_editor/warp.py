"""Tool - Time Warp: non-linear retiming with live preview.

Keys inside the time range of the selection (across curves) are re-spaced
along an easing curve; the first and last selected frames stay put, so
nothing outside the range moves.  Values never change, only timing:

  Ease In      keys bunch up at the start (slow in), spread towards the end
  Ease Out     the opposite
  Ease In/Out  bunch up at both ends

The slider blends from linear (0%) to the full easing (100%).  Handle
x-lengths follow the local stretch so the shape between keys is kept.
"""

import bpy
import numpy as np

from . import common, slider


def ease(u, shape):
    """(g(u), g'(u)) for u in [0, 1]."""
    if shape == 'EASE_IN':
        return u * u, 2.0 * u
    if shape == 'EASE_OUT':
        return 1.0 - (1.0 - u) ** 2, 2.0 * (1.0 - u)
    return u * u * (3.0 - 2.0 * u), 6.0 * u * (1.0 - u)


def warp_times(x, t0, t1, amount, shape):
    """(new x, local stretch factor) for keys strictly inside (t0, t1)."""
    x = np.asarray(x, dtype=np.float64)
    nx = x.copy()
    stretch = np.ones_like(x)
    if t1 - t0 < 1e-9:
        return nx, stretch
    inside = (x > t0) & (x < t1)
    u = (x[inside] - t0) / (t1 - t0)
    g, dg = ease(u, shape)
    a = amount / 100.0
    nx[inside] = t0 + (t1 - t0) * ((1.0 - a) * u + a * g)
    stretch[inside] = (1.0 - a) + a * dg
    return nx, stretch


def warp_curve(snap, t0, t1, amount, shape):
    nx, stretch = warp_times(snap.co[:, 0], t0, t1, amount, shape)
    x = snap.co[:, 0]
    co, hl, hr = snap.co.copy(), snap.hl.copy(), snap.hr.copy()
    co[:, 0] = nx
    # keep handles usable even where the easing is flat
    k = np.maximum(stretch, 0.05)
    hl[:, 0] = nx + (snap.hl[:, 0] - x) * k
    hr[:, 0] = nx + (snap.hr[:, 0] - x) * k
    return co, hl, hr


class WarpTool(slider.SliderTool):
    id = "warp"
    label = "TIME WARP"
    op_label = "Time Warp"
    description = ("Ease the timing of the keys inside the selected time range "
                   "(slow in / slow out) with a live preview. Range ends stay put")
    setting = "warp_amount"
    vmin, vmax = 0.0, 100.0
    snap_step = 10.0

    def prepare(self, context):
        jobs = slider.selected_jobs(context)
        sel_x = [x for j in jobs for x in j.snap.co[j.snap.selected, 0]]
        if not sel_x or max(sel_x) - min(sel_x) < 1e-4:
            return "Select keys spanning at least two different frames"
        self.t0, self.t1 = min(sel_x), max(sel_x)
        self.shape = common.get_settings(context).warp_shape
        return jobs

    def compute(self, job, value):
        return warp_curve(job.snap, self.t0, self.t1, value, self.shape)

    def describe(self, value):
        names = {'EASE_IN': "ease in", 'EASE_OUT': "ease out", 'EASE_IN_OUT': "ease in/out"}
        return "%.0f%% %s   (frames %.0f-%.0f)" % (value, names.get(self.shape, ""),
                                                  getattr(self, "t0", 0), getattr(self, "t1", 0))


TOOL = WarpTool()


class MGE_PT_warp(bpy.types.Panel):
    bl_label = "Time Warp"
    bl_idname = "MGE_PT_warp"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 9

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        st = common.get_settings(context)
        self.layout.row().prop(st, "warp_shape", expand=True)
        slider.draw_panel(self.layout, context, TOOL, 'TIME')


classes = (slider.make_operator(TOOL), MGE_PT_warp)


def register_tool():
    pass


def unregister_tool():
    slider.unregister_tool_session(TOOL.id)
