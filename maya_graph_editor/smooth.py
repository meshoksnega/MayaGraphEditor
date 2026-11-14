"""Tool - Smooth with live preview.

Gaussian smoothing of the selected keys' values over time (a weighted local
line fit, so steady motion stays straight).  The slider is
the blur width (sigma, in frames).  The first and last key of every
selected run stay put so the smoothed part joins the rest of the curve
without a jump; unselected keys never move but still feed the average.
"""

import bpy
import numpy as np

from . import common, slider, tween


def smooth_values(x, y, sel, sigma):
    """Gaussian-smoothed values for the selected interior keys of each run."""
    y = np.asarray(y, dtype=np.float64)
    out = y.copy()
    if sigma <= 1e-6:
        return out
    x = np.asarray(x, dtype=np.float64)
    idx = np.flatnonzero(sel)
    if len(idx) < 3:
        return out
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    reach = 3.0 * sigma
    for run in runs:
        for i in run[1:-1]:
            lo = np.searchsorted(x, x[i] - reach, 'left')
            hi = np.searchsorted(x, x[i] + reach, 'right')
            dx = x[lo:hi] - x[i]
            w = np.exp(-0.5 * (dx / sigma) ** 2)
            yw = y[lo:hi]
            # Gaussian-weighted local *line* fit: a plain weighted mean gets
            # lopsided near run ends and bends steady motion; a line fit keeps
            # straight motion straight and still removes jitter.
            s0, s1, s2 = w.sum(), np.dot(w, dx), np.dot(w, dx * dx)
            t0, t1 = np.dot(w, yw), np.dot(w, dx * yw)
            det = s0 * s2 - s1 * s1
            out[i] = float((s2 * t0 - s1 * t1) / det) if det > 1e-12 * s0 * s0 else float(t0 / s0)
    return out


class SmoothTool(slider.SliderTool):
    id = "smooth"
    label = "SMOOTH"
    op_label = "Smooth Selected Keys"
    description = ("Smooth the selected keys (Gaussian blur over time) with a live preview. "
                   "Ends of each selected run stay in place")
    setting = "smooth_sigma"
    vmin, vmax = 0.0, 20.0
    snap_step = 1.0

    def prepare(self, context):
        jobs = slider.selected_jobs(context, need=3)
        return jobs or "Select at least 3 consecutive keys on a curve"

    def compute(self, job, value):
        s = job.snap
        new_y = smooth_values(s.co[:, 0], s.co[:, 1], s.selected, value)
        return tween.shifted(s, new_y)

    def describe(self, value):
        return "blur %.1f frames" % value


TOOL = SmoothTool()


class MGE_PT_smooth(bpy.types.Panel):
    bl_label = "Smooth"
    bl_idname = "MGE_PT_smooth"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 7

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        slider.draw_panel(self.layout, context, TOOL, 'SMOOTHCURVE')


classes = (slider.make_operator(TOOL), MGE_PT_smooth)


def register_tool():
    pass


def unregister_tool():
    slider.unregister_tool_session(TOOL.id)
