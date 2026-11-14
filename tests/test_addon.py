"""Headless integration tests (run with a `bpy` Python:  python tests/test_addon.py).

UI-only parts (drawing, modal events) cannot run without a Blender window;
everything underneath them is exercised here against real F-Curves.
"""
import os
import sys
import types

import numpy as np
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from bpy_helpers import make_curve, select_all  # noqa: E402

import maya_graph_editor as addon  # noqa: E402
from maya_graph_editor import common, core, ghost, retime, simplify, tangents  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def state(fc):
    return [(tuple(round(v, 5) for v in k.co), tuple(round(v, 5) for v in k.handle_left),
             tuple(round(v, 5) for v in k.handle_right), k.handle_left_type,
             k.handle_right_type, k.interpolation) for k in fc.keyframe_points]


# ---------------------------------------------------------------------------
print("registration / independent toggles")
flags = {n: True for n in common.TOOL_IDS}
fake = types.SimpleNamespace(**{"enable_" + n: True for n in common.TOOL_IDS})
common.get_prefs = lambda: fake
addon.register()
check(core._active == set(common.TOOL_IDS), "all four tools registered")
check(hasattr(bpy.ops.mge, "set_tangent") and hasattr(bpy.ops.mge, "ghost_snapshot")
      and hasattr(bpy.ops.mge, "simplify") and hasattr(bpy.ops.mge, "retime"),
      "operators exist")
for name in common.TOOL_IDS:
    setattr(fake, "enable_" + name, False)
    core.sync_tools()
    check(name not in core._active and core._active == set(common.TOOL_IDS) - {name},
          "disabling '%s' leaves the other three registered" % name)
    cls = core.TOOLS[[t[0] for t in core.TOOLS].index(name)][1].classes[0]
    check(not cls.is_registered if hasattr(cls, "is_registered") else True,
          "  '%s' operator class unregistered" % name)
    setattr(fake, "enable_" + name, True)
    core.sync_tools()
    check(name in core._active, "re-enabling '%s' works" % name)
scene = bpy.context.scene
check(scene.mge_settings.simplify_tolerance == 2.0, "scene settings exist")

# ---------------------------------------------------------------------------
print("snapshot round trip (mixed handle types / interpolation)")
fc = make_curve([(1, 0), (10, 5), (20, -3), (30, 2), (40, 2.5)], obj_name="RT")
ks = fc.keyframe_points
ks[1].handle_left_type = ks[1].handle_right_type = 'ALIGNED'
ks[1].handle_left = (6.0, 4.0); ks[1].handle_right = (14.0, 6.0)
ks[2].handle_left_type = ks[2].handle_right_type = 'FREE'
ks[2].handle_left = (16.0, -1.0); ks[2].handle_right = (24.0, -5.5)
ks[3].handle_left_type = ks[3].handle_right_type = 'VECTOR'
ks[0].interpolation = 'LINEAR'; ks[3].interpolation = 'CONSTANT'
select_all(fc); ks[2].select_control_point = False
fc.update()
before = state(fc)
snap = common.CurveSnapshot.of(fc)
snap.write(fc, keep=[0, 1, 4])
check(len(fc.keyframe_points) == 3, "write(keep=...) drops keys")
snap.write(fc)
check(state(fc) == before, "full restore reproduces keys, handles, types, interpolation")
check([k.select_control_point for k in fc.keyframe_points] == [True, True, False, True, True],
      "selection flags restored")

# ---------------------------------------------------------------------------
print("tangent types")
def fresh():
    f = make_curve([(1, 0), (10, 5), (20, 1), (30, 4), (40, 4.5)], obj_name="TG", handle='FREE')
    select_all(f)
    return f
f = fresh()
check(tangents.apply_tangent(f, 'SPLINE') == 5 and all(
    k.handle_left_type == 'AUTO' and k.interpolation == 'BEZIER' for k in f.keyframe_points), "Spline")
f = fresh(); tangents.apply_tangent(f, 'CLAMPED')
check(all(k.handle_right_type == 'AUTO_CLAMPED' for k in f.keyframe_points), "Clamped")
f = fresh(); tangents.apply_tangent(f, 'LINEAR')
check(all(k.interpolation == 'LINEAR' for k in f.keyframe_points), "Linear")
f = fresh(); tangents.apply_tangent(f, 'STEPPED')
check(all(k.interpolation == 'CONSTANT' for k in f.keyframe_points), "Stepped")
f = fresh(); tangents.apply_tangent(f, 'FLAT')
check(all(abs(k.handle_left[1] - k.co[1]) < 1e-5 and abs(k.handle_right[1] - k.co[1]) < 1e-5
          for k in f.keyframe_points), "Flat (all handles horizontal)")
f = fresh(); tangents.apply_tangent(f, 'PLATEAU')
kk = f.keyframe_points
flat = [abs(k.handle_right[1] - k.co[1]) < 1e-5 for k in kk]
# values 0,5,1,4,4.5 -> extremes at idx 0(end),1(max),2(min),4(end); idx3 is not an extreme
check(flat == [True, True, True, False, True], "Plateau flat only at extremes/ends: %s" % flat)
f = fresh()
for i, k in enumerate(f.keyframe_points):
    k.select_control_point = k.select_left_handle = k.select_right_handle = (i in (1, 2))
tangents.apply_tangent(f, 'STEPPED')
check([k.interpolation for k in f.keyframe_points] == ['BEZIER', 'CONSTANT', 'CONSTANT', 'BEZIER', 'BEZIER'],
      "only selected keys change")
f = fresh(); select_all(f, False)
check(tangents.apply_tangent(f, 'SPLINE') == 0, "no selection -> nothing changes")

# ---------------------------------------------------------------------------
print("ghost / buffer curve")
f = make_curve([(1, 0), (10, 5), (20, 1)], obj_name="GH")
select_all(f)
orig = state(f)
n = ghost.take_snapshot([f])
check(n == 1 and ghost.buffer_count() == 1, "snapshot stored")
buf = ghost._buffers[common.curve_key(f)]
check(buf.samples.shape[1] == 2 and buf.samples[0, 0] == 1 and buf.samples[-1, 0] == 20, "samples span the key range")
check(abs(buf.samples[-1, 1] - 1) < 1e-4, "samples follow the curve")
f.keyframe_points[1].co = (10, 9.0); f.keyframe_points[1].handle_left[1] = 9; f.update()
edited = state(f)
check(ghost._buffers[common.curve_key(f)].samples is buf.samples, "editing the curve does not touch the ghost")
ghost.swap_with_buffer([f])
check(state(f) == orig, "swap restores the buffered shape")
swapped = ghost._buffers[common.curve_key(f)]
check(abs(swapped.samples[np.argmin(abs(swapped.samples[:, 0] - 10)), 1] - 9.0) < 1e-3, "swap stores the edited shape as new ghost")
ghost.clear_buffers()
check(ghost.buffer_count() == 0, "clear")

# ---------------------------------------------------------------------------
print("display mapping")
rot = make_curve([(1, 0), (10, 1.5)], path="rotation_euler", index=0, obj_name="ROT")
loc = make_curve([(1, 0), (10, 1.5)], path="location", index=0, obj_name="ROT")
check(common.curve_is_angle(rot) is True, "rotation_euler is an angle (degrees)")
check(common.curve_is_angle(loc) is False, "location is not an angle")
sp = types.SimpleNamespace(use_normalization=False)
check(abs(common.display_mapping(rot, sp, scene)[0] - 57.29578) < 1e-3, "degrees scale applied")
sp.use_normalization = True
fac, off = common.display_mapping(loc, sp, scene)
check(abs((0 + off) * fac + 1) < 1e-6 and abs((1.5 + off) * fac - 1) < 1e-6, "normalisation maps to [-1, 1]")

# ---------------------------------------------------------------------------
print("retime")
def two_curves():
    a = make_curve([(1, 0), (11, 5), (21, 1), (31, 3), (41, 0)], path="location", index=0, obj_name="RTA")
    b = make_curve([(1, 2), (11, 2), (21, 8), (31, 8), (41, 6)], path="location", index=1, obj_name="RTA")
    return a, b
a, b = two_curves()
for fc_ in (a, b):
    for i, k in enumerate(fc_.keyframe_points):
        s = i in (1, 2, 3)
        k.select_control_point = k.select_left_handle = k.select_right_handle = s
rng = retime.selection_range([common.CurveSnapshot.of(a), common.CurveSnapshot.of(b)])
check(rng == (11.0, 31.0), "range spans both curves: %s" % (rng,))
sa = common.CurveSnapshot.of(a)
co, hl, hr = retime.retime_curve(sa, 11, 31, 11, 51, True)   # stretch x2 about left edge
check(list(co[:, 0]) == [1, 11, 31, 51, 61], "x2 stretch + ripple: %s" % list(co[:, 0]))
check(np.allclose(co[:, 1], sa.co[:, 1]), "values untouched")
check(np.allclose((hr[1:4, 0] - co[1:4, 0]), (sa.hr[1:4, 0] - sa.co[1:4, 0]) * 2), "handle x-lengths scale with the stretch")
co2, _, _ = retime.retime_curve(sa, 11, 31, 11, 51, False)
check(list(co2[:, 0]) == [1, 11, 31, 51, 41], "no ripple leaves later key alone")
co3, _, _ = retime.retime_curve(sa, 11, 31, 11, 21, True)    # compress to half
check(list(co3[:, 0]) == [1, 11, 16, 21, 31], "compress + ripple: %s" % list(co3[:, 0]))
co4, _, _ = retime.retime_curve(sa, 11, 31, 1, 31, True)     # drag left edge outwards
check(co4[0, 0] == -9.0 or co4[0, 0] == 1 + (1 - 11), "left-edge drag ripples earlier keys")
# apply to real curves and verify shape (values at scaled times identical)
orig_vals = [a.evaluate(float(x)) for x in (11, 16, 21, 26, 31)]
sa.write(a, co=co, hl=hl, hr=hr)
new_vals = [a.evaluate(float(x)) for x in (11, 21, 31, 41, 51)]
check(np.allclose(orig_vals, new_vals, atol=1e-4), "retimed curve hits the same values at the scaled times")
mid_old = [common.CurveSnapshot.of(a)]
check(all(a.keyframe_points[i].co[0] < a.keyframe_points[i + 1].co[0] for i in range(4)), "keys stay ordered")

# ---------------------------------------------------------------------------
print("simplify (plan / preview / cancel / apply)")
frames = np.arange(1, 101)
vals = np.sin(frames / 7.0) * 3 + np.random.default_rng(1).normal(0, 0.05, len(frames))
fc = make_curve(list(zip(frames.tolist(), vals.tolist())), obj_name="SIMP")
select_all(fc)
for k in fc.keyframe_points:   # select only 10..90
    on = 10 <= k.co[0] <= 90
    k.select_control_point = k.select_left_handle = k.select_right_handle = on
before = state(fc)
plan = simplify.build_curve_plan(fc)
check(plan is not None and len(plan.order) == 79, "plan covers the 79 interior selected keys (ends kept)")
ses = types.SimpleNamespace(plans=[plan])
last_n = 100
for pct in (0.5, 2, 5, 15):
    cnt = simplify_core = None
    from maya_graph_editor import simplify_core as sc
    cnt = sc.removal_count(plan.cum, plan.span * pct / 100)
    keep = np.setdiff1d(np.arange(plan.snap.n), plan.order[:cnt])
    plan.snap.write(fc, keep=keep)
    n_now = len(fc.keyframe_points)
    check(n_now == 100 - cnt and n_now <= last_n, "tol %4.1f%%: %3d keys left" % (pct, n_now))
    last_n = n_now
    xs = [k.co[0] for k in fc.keyframe_points]
    check(xs[0] == 1 and xs[-1] == 100 and 10 in xs and 90 in xs, "   run ends and unselected keys kept")
plan.snap.write(fc)
check(state(fc) == before, "cancel (restore) is exact")

# ---------------------------------------------------------------------------
print("unregister")
addon.unregister()
check(core._active == set() and not hasattr(bpy.types.Scene, "mge_settings"), "clean unregister")

print()
print("FAILURES: %d" % len(FAILS))
for m in FAILS:
    print("  -", m)
sys.exit(1 if FAILS else 0)
