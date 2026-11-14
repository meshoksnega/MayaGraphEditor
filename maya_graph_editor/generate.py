"""Tools - Noise and Settle (live preview).

Noise
    Adds smooth random variation to the selected keys.  Amount is a
    percentage of each curve's value range over the selection; Scale is how
    many frames one wiggle takes; Seed gives a different pattern.  Each
    curve gets its own pattern, and the same seed always gives the same result.
Settle
    Adds a decaying wobble after the last selected key, as if the motion
    overshoots and comes to rest.  The wobble's size follows how fast the
    curve was moving into that key.  It replaces keys inside the settle length.
"""

import math
import zlib

import bpy
import numpy as np

from . import common, slider, tween


def smooth_noise(x, seed):
    """Deterministic smooth 1D noise in [-1, 1]."""
    table = np.random.RandomState(seed % (2 ** 31)).uniform(-1.0, 1.0, 256)
    x = np.asarray(x, dtype=np.float64)
    i = np.floor(x).astype(np.int64)
    f = x - i
    f = f * f * (3.0 - 2.0 * f)
    return table[i % 256] * (1.0 - f) + table[(i + 1) % 256] * f


def noise_values(x, y, sel, amount_pct, scale, seed):
    y = np.asarray(y, dtype=np.float64)
    out = y.copy()
    if not sel.any() or amount_pct == 0:
        return out
    span = float(y[sel].max() - y[sel].min())
    amp = (span if span > 1e-9 else 1.0) * amount_pct / 100.0
    out[sel] = y[sel] + amp * smooth_noise(np.asarray(x)[sel] / max(scale, 1e-3), seed)
    return out


def settle_snapshot(snap, amount_pct, period, length):
    """Snapshot with a decaying wobble after the last selected key."""
    sel = np.flatnonzero(snap.selected)
    if not len(sel) or amount_pct == 0:
        return snap
    i = int(sel[-1])
    x0, y0 = snap.co[i]
    if i > 0 and x0 - snap.co[i - 1, 0] > 1e-9:
        vel = (y0 - snap.co[i - 1, 1]) / (x0 - snap.co[i - 1, 0])
    else:
        vel = 0.0
    if abs(vel) < 1e-12:
        return snap
    w = 2.0 * math.pi / max(period, 1e-3)
    decay = 4.0 / max(length, 1e-3)
    step = max(1.0, round(period / 4.0))
    ts = np.arange(step, length + 1e-6, step)
    ys = y0 + (vel / w) * (amount_pct / 100.0) * np.exp(-decay * ts) * np.sin(w * ts)
    ys[-1] = y0  # come to rest exactly
    gen = common.CurveSnapshot.build(x0 + ts, ys, selected=False, extrapolation=snap.extrapolation)
    keep = (snap.co[:, 0] <= x0 + 1e-6) | (snap.co[:, 0] > x0 + length + 1e-6)
    out = common.CurveSnapshot.concat([snap.subset(keep), gen])
    out.extrapolation = snap.extrapolation
    return out


class NoiseTool(slider.SliderTool):
    id = "noise"
    label = "NOISE"
    op_label = "Add Noise"
    description = "Add smooth random variation to the selected keys, with a live preview"
    setting = "noise_amount"
    vmin, vmax = 0.0, 50.0
    snap_step = 5.0

    def prepare(self, context):
        st = common.get_settings(context)
        self.scale, self.seed = st.noise_scale, st.noise_seed
        jobs = slider.selected_jobs(context)
        for j in jobs:
            j.data = zlib.crc32(("%s|%d" % (j.key[1], j.key[2])).encode())
        return jobs or "Select keyframes first"

    def compute(self, job, value):
        s = job.snap
        new_y = noise_values(s.co[:, 0], s.co[:, 1], s.selected, value, self.scale,
                             self.seed * 7919 + job.data)
        return tween.shifted(s, new_y)

    def describe(self, value):
        return "%.1f%% of the value range" % value


class SettleTool(slider.SliderTool):
    id = "settle"
    label = "SETTLE"
    op_label = "Add Settle"
    description = ("Add a decaying wobble after the last selected key, sized by how fast the "
                   "curve was moving, with a live preview")
    setting = "settle_amount"
    vmin, vmax = 0.0, 200.0
    snap_step = 25.0
    marks = (100.0,)

    def prepare(self, context):
        st = common.get_settings(context)
        self.period, self.length = st.settle_period, st.settle_length
        return slider.selected_jobs(context) or "Select the key where the motion should settle"

    def write(self, job, fc, value):
        settle_snapshot(job.snap, value, self.period, self.length).write(fc)

    def describe(self, value):
        return "%.0f%%   (%.0f frames, wobble every %.0f)" % (
            value, getattr(self, "length", 0), getattr(self, "period", 0))


NOISE = NoiseTool()
SETTLE = SettleTool()


class MGE_PT_generate(bpy.types.Panel):
    bl_label = "Noise / Settle"
    bl_idname = "MGE_PT_generate"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 14
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        box = layout.box()
        box.label(text="Noise")
        row = box.row(align=True)
        row.prop(st, "noise_scale")
        row.prop(st, "noise_seed")
        slider.draw_panel(box, context, NOISE, 'RNDCURVE')
        box = layout.box()
        box.label(text="Settle")
        row = box.row(align=True)
        row.prop(st, "settle_period")
        row.prop(st, "settle_length")
        slider.draw_panel(box, context, SETTLE, 'FORCE_HARMONIC')


classes = (slider.make_operator(NOISE), slider.make_operator(SETTLE), MGE_PT_generate)


def register_tool():
    pass


def unregister_tool():
    slider.unregister_tool_session(NOISE.id)
    slider.unregister_tool_session(SETTLE.id)
