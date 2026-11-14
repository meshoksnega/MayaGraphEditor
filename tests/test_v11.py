"""Headless tests for the v1.1 features (python tests/test_v11.py with a `bpy` Python)."""
import os
import sys
import tempfile
import types

import numpy as np
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from bpy_helpers import make_curve, select_all  # noqa: E402

import maya_graph_editor as addon  # noqa: E402
from maya_graph_editor import (common, core, curves, ghost, keymaps, retime,  # noqa: E402
                               simplify, simplify_core, stats, tangents)

FAILS = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def sel_only(fc, idx):
    for i, k in enumerate(fc.keyframe_points):
        on = i in idx
        k.select_control_point = k.select_left_handle = k.select_right_handle = on


fake = types.SimpleNamespace(**{"enable_" + n: True for n in common.TOOL_IDS},
                             show_header_tangents=False)
common.get_prefs = lambda: fake
addon.register()
scene = bpy.context.scene
st = scene.mge_settings
_curves = []
common.editable_fcurves = lambda context=None: list(_curves)  # no Graph Editor in background

# ---------------------------------------------------------------------------
print("tools and shortcuts")
check(core._active == set(common.TOOL_IDS), "six tools registered: %s" % sorted(core._active))
check(set(keymaps._items) == {"tangents", "ghost", "simplify", "retime"}, "shortcuts registered per tool")
fake.enable_simplify = False
core.sync_tools()
check("simplify" not in keymaps._items, "disabling a tool removes its shortcut")
fake.enable_simplify = True
core.sync_tools()
check("simplify" in keymaps._items, "re-enabling restores it")

# ---------------------------------------------------------------------------
print("tangents: sides, break, unify, new-key default")
def tcurve():
    f = make_curve([(1, 0), (10, 5), (20, 1), (30, 4)], obj_name="T11", handle='AUTO_CLAMPED')
    return f
f = tcurve(); sel_only(f, [2])
k = f.keyframe_points[2]
right_before = tuple(k.handle_right)
tangents.apply_tangent(f, 'FLAT', 'IN')
k = f.keyframe_points[2]
check(abs(k.handle_left[1] - k.co[1]) < 1e-6, "In-only Flat flattens the left handle")
check(np.allclose(tuple(k.handle_right), right_before, atol=1e-5), "  and leaves the right handle where it was")
check(k.handle_left_type == 'FREE' and k.handle_right_type == 'FREE', "  handles broken to keep both sides")
f = tcurve(); sel_only(f, [2])
tangents.apply_tangent(f, 'STEPPED', 'IN')
check([kk.interpolation for kk in f.keyframe_points] == ['BEZIER', 'CONSTANT', 'BEZIER', 'BEZIER'],
      "In-only Stepped changes the segment entering the key")
f = tcurve(); sel_only(f, [2])
tangents.apply_tangent(f, 'LINEAR', 'OUT')
check([kk.interpolation for kk in f.keyframe_points] == ['BEZIER', 'BEZIER', 'LINEAR', 'BEZIER'],
      "Out-only Linear changes the segment leaving the key")
f = tcurve(); sel_only(f, [1])
tangents.apply_tangent(f, 'SPLINE', 'OUT')
k = f.keyframe_points[1]
check(k.handle_right_type == 'AUTO' and k.handle_left_type == 'AUTO_CLAMPED', "Out-only Spline: one side's type")

f = tcurve(); sel_only(f, [1])
tangents.break_tangents(f)
k = f.keyframe_points[1]
check(k.handle_left_type == 'FREE' and k.handle_right_type == 'FREE', "Break -> free handles")
k.handle_left = (k.handle_left[0], k.co[1] + 2.0)   # broken: left points down into the key
k.handle_right = (k.handle_right[0], k.co[1] + 1.0)  # right points up
f.update()
tangents.unify_tangents(f)
k = f.keyframe_points[1]
sl = (k.co[1] - k.handle_left[1]) / (k.co[0] - k.handle_left[0])
sr = (k.handle_right[1] - k.co[1]) / (k.handle_right[0] - k.co[0])
check(abs(sl - sr) < 1e-4 and k.handle_left_type == 'ALIGNED', "Unify -> collinear aligned handles (%.3f / %.3f)" % (sl, sr))

edit = bpy.context.preferences.edit
saved = (edit.keyframe_new_interpolation_type, edit.keyframe_new_handle_type)
st.new_key_tangent = 'SPLINE'
check((edit.keyframe_new_interpolation_type, edit.keyframe_new_handle_type) == ('BEZIER', 'AUTO'),
      "New Keys: Spline writes Blender's preference")
st.new_key_tangent = 'STEPPED'
check(edit.keyframe_new_interpolation_type == 'CONSTANT' and st.new_key_tangent == 'STEPPED',
      "New Keys: Stepped round-trips")
edit.keyframe_new_interpolation_type, edit.keyframe_new_handle_type = 'BEZIER', 'VECTOR'
check(st.new_key_tangent == 'OTHER', "unrecognised preference shows Custom")
edit.keyframe_new_interpolation_type, edit.keyframe_new_handle_type = saved

# ---------------------------------------------------------------------------
print("curves: infinity")
f = make_curve([(1, 0), (11, 4), (21, 1)], obj_name="INF")
check(curves.get_infinity(f, 'PRE') == 'CONSTANT', "default constant")
curves.set_infinity(f, 'POST', 'CYCLE')
check(curves.get_infinity(f, 'POST') == 'CYCLE' and curves.get_infinity(f, 'PRE') == 'CONSTANT',
      "post Cycle only")
check(abs(f.evaluate(31) - f.evaluate(11)) < 1e-4, "  curve repeats after the last key")
curves.set_infinity(f, 'PRE', 'OSCILLATE')
check(curves.get_infinity(f, 'PRE') == 'OSCILLATE' and curves.get_infinity(f, 'POST') == 'CYCLE',
      "pre Oscillate keeps post Cycle")
curves.set_infinity(f, 'POST', 'CYCLE_OFFSET')
check(abs(f.evaluate(31) - (f.evaluate(11) + 1.0)) < 1e-3, "cycle with offset adds the value change per cycle")
shared = curves.set_infinity(f, 'BOTH', 'LINEAR')
check(not any(m.type == 'CYCLES' for m in f.modifiers) and f.extrapolation == 'LINEAR',
      "Both Linear removes the cycles modifier")
shared = curves.set_infinity(f, 'PRE', 'CONSTANT')
check(shared and curves.get_infinity(f, 'POST') == 'CONSTANT', "shared Constant/Linear reported")

# ---------------------------------------------------------------------------
print("key stats")
a = make_curve([(1, 0), (10, 2), (20, 4)], obj_name="ST", path="location", index=0)
b = make_curve([(5, 1), (15, 3)], obj_name="ST", path="location", index=1)
sel_only(a, [1, 2]); sel_only(b, [0])
_curves[:] = [a, b]
st.stats_mode = 'ABSOLUTE'
check(abs(st.stats_frame - 5) < 1e-6, "frame shows first selected frame (5)")
check(abs(st.stats_value - (2 + 4 + 1) / 3) < 1e-6, "value shows the average")
st.stats_frame = 8
check([k.co[0] for k in a.keyframe_points] == [1, 13, 23] and b.keyframe_points[0].co[0] == 8,
      "absolute frame moves the whole selection, spacing kept")
hl_before = tuple(a.keyframe_points[1].handle_left)
st.stats_value = 7
check(all(abs(a.keyframe_points[i].co[1] - 7) < 1e-6 for i in (1, 2)) and abs(b.keyframe_points[0].co[1] - 7) < 1e-6,
      "absolute value sets every selected key")
check(abs(a.keyframe_points[0].co[1]) < 1e-6, "unselected key untouched")
st.stats_mode = 'RELATIVE'
check(st.stats_frame == 0.0, "relative starts at 0")
st.stats_frame = 1.0
st.stats_frame = 2.5   # a drag sends running totals
check([k.co[0] for k in a.keyframe_points] == [1, 15.5, 25.5], "relative drag totals don't compound: %s"
      % [k.co[0] for k in a.keyframe_points])
st.stats_value = -1
check(abs(a.keyframe_points[1].co[1] - 6) < 1e-6, "relative value offset")
r = make_curve([(1, 0), (10, 1.0)], obj_name="STR", path="rotation_euler", index=2)
sel_only(r, [1]); _curves[:] = [r]
st.stats_mode = 'ABSOLUTE'
check(abs(st.stats_value - 57.29578) < 1e-3, "rotation shown in degrees")
st.stats_value = 90
check(abs(r.keyframe_points[1].co[1] - np.pi / 2) < 1e-5, "degrees typed -> radians stored")
_curves[:] = []

# ---------------------------------------------------------------------------
print("ghost: slots, range, dashes, saved in file")
g = make_curve([(1, 0), (10, 5), (20, 1)], obj_name="GH11")
curves.set_infinity(g, 'POST', 'CYCLE')
ghost.take_snapshot([g], 'A', scene, st)
g.keyframe_points[1].co = (10, 8); g.update()
ghost.take_snapshot([g], 'B', scene, st)
check(ghost.buffer_count('A') == 1 and ghost.buffer_count('B') == 1, "independent slots A and B")
check(ghost._buffers[('A', common.curve_key(g))].samples[:, 1].max() < ghost._buffers[('B', common.curve_key(g))].samples[:, 1].max(),
      "slots hold different shapes")
st.ghost_range = 'SCENE'
scene.frame_start, scene.frame_end = 1, 60
ghost.take_snapshot([g], 'C', scene, st)
sc = ghost._buffers[('C', common.curve_key(g))].samples
check(sc[0, 0] == 1 and sc[-1, 0] == 60, "scene-range ghost covers frames 1-60 (incl. cycles)")
st.ghost_range = 'KEYS'
segs = ghost.dash_segments(np.linspace(0, 100, 50), np.zeros(50))
check(40 < sum(x1 - x0 for x0, _, x1, _ in segs) < 65, "dashes cover ~8/14 of the line")
ghost.clear_buffers('C')
check(ghost.buffer_count() == 2, "clear one slot")

path = os.path.join(tempfile.mkdtemp(), "ghosts.blend")
st.ghost_save = True
bpy.ops.wm.save_as_mainfile(filepath=path)
ghost.clear_buffers()
bpy.ops.wm.open_mainfile(filepath=path)
check(ghost.buffer_count() == 2, "ghosts restored after reopening the .blend (%d)" % ghost.buffer_count())
g2 = [c for c in bpy.data.objects["GH11"].animation_data.action.layers[0].strips[0].channelbags[0].fcurves][0] \
    if hasattr(bpy.data.actions[0], "layers") else None
buf = ghost._buffers.get(('A', common.curve_key(g2))) if g2 else None
check(buf is not None and buf.keys.n == 3, "restored buffer keeps its keys (Swap still works)")
if g2:
    ghost.swap_with_buffer([g2], 'A')
    check(abs(g2.keyframe_points[1].co[1] - 5) < 1e-6, "swap with a restored ghost")
bpy.context.scene.mge_settings.ghost_save = False
bpy.ops.wm.save_as_mainfile(filepath=path)
check(all(ghost.PROP not in act for act in bpy.data.actions), "Save Ghosts off removes them from the file")
scene = bpy.context.scene
st = scene.mge_settings

# ---------------------------------------------------------------------------
print("retime numeric scale")
check(retime.scaled_range(10, 20, 150, 'LEFT') == (10, 25), "150% about start")
check(retime.scaled_range(10, 20, 50, 'RIGHT') == (15, 20), "50% about end")
check(retime.scaled_range(10, 20, 200, 'CENTER') == (5, 25), "200% about centre")
rt = make_curve([(1, 0), (11, 5), (21, 1), (31, 3)], obj_name="RT11")
sel_only(rt, [1, 2])
_curves[:] = [rt]
st.retime_ripple = True
ctx = types.SimpleNamespace(area=types.SimpleNamespace(as_pointer=lambda: 1), scene=scene)
res = retime.scale_selection(ctx, 200, 'LEFT')
check(res == (11, 31) and [k.co[0] for k in rt.keyframe_points] == [1, 11, 31, 41],
      "scale selection 200%% without the lattice: %s" % [k.co[0] for k in rt.keyframe_points])
_curves[:] = []

# ---------------------------------------------------------------------------
print("simplify: background analysis equals direct analysis")
fr = np.arange(1, 401)
vals = np.sin(fr / 13.0) * 2 + np.random.default_rng(5).normal(0, 0.05, len(fr))
sfc = make_curve(list(zip(fr.tolist(), vals.tolist())), obj_name="SA")
select_all(sfc)
direct = simplify.build_curve_plan(sfc)
lazy = simplify.build_curve_plan(sfc, analyse=False)
check(lazy.order is None and lazy.planner is not None, "analysis deferred")
ses = simplify.Session(types.SimpleNamespace(as_pointer=lambda: 1), [lazy])
ticks = 0
while not ses.step(budget=0.01):
    ticks += 1
    check(0.0 <= ses.progress <= 1.0, "progress %.2f" % ses.progress) if ticks == 1 else None
check(ticks > 1, "spread over %d ticks" % ticks)
check(np.array_equal(direct.order, lazy.order) and np.allclose(direct.cum, lazy.cum),
      "same removal order as the direct analysis")

# ---------------------------------------------------------------------------
print("updater marker")
from maya_graph_editor import updater  # noqa: E402
updater._write_marker("Updated to v9")
updater._set(status="IDLE", message="")
updater.restore_message()
check(updater.get_state()["status"] == "INSTALLED" and "v9" in updater.get_state()["message"],
      "update message survives a reload")
check(not os.path.exists(updater.MARKER), "marker consumed")

addon.unregister()
check(not keymaps._items, "shortcuts removed on unregister")
print()
print("FAILURES: %d" % len(FAILS))
for m in FAILS:
    print("  -", m)
sys.exit(1 if FAILS else 0)
