"""Validate the simplify model against Blender's real curve evaluation."""
import importlib.util
import os
import sys

import numpy as np
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bpy_helpers import make_curve, select_all  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "simplify_core", os.path.join(HERE, "..", "maya_graph_editor", "simplify_core.py"))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

rng = np.random.default_rng(3)


def dense(fc, step=0.25):
    ks = fc.keyframe_points
    xs = np.arange(ks[0].co[0], ks[len(ks) - 1].co[0] + 1e-6, step)
    return xs, np.array([fc.evaluate(float(x)) for x in xs])


def blender_curve_arrays(fc):
    ks = fc.keyframe_points
    n = len(ks)
    co = np.array([tuple(k.co) for k in ks])
    hl = np.array([tuple(k.handle_left) for k in ks])
    hr = np.array([tuple(k.handle_right) for k in ks])
    return (co, hl, hr, [k.handle_left_type for k in ks],
            [k.handle_right_type for k in ks], [k.interpolation for k in ks])


def run_case(name, handle, smoothing='CONT_ACCEL'):
    frames = np.arange(1, 121, 2)
    vals = np.sin(frames / 9.0) * 2 + rng.normal(0, 0.12, len(frames))
    fc = make_curve(list(zip(frames.tolist(), vals.tolist())),
                    obj_name="Obj_%s_%s" % (name, smoothing), handle=handle)
    fc.auto_smoothing = smoothing
    fc.update()
    select_all(fc)
    co, hl, hr, lt, rt, ipo = blender_curve_arrays(fc)
    xs, ys = dense(fc)
    removable = np.zeros(len(co), bool)
    removable[1:-1] = True
    order, cum = core.build_plan(co, hl, hr, lt, rt, ipo, removable, xs, ys,
                                 fc.extrapolation == 'CONSTANT', fc.auto_smoothing)
    span = ys.max() - ys.min()
    print("[%s/%s] keys=%d removable order=%d span=%.2f" % (name, smoothing, len(co), len(order), span))
    ok = True
    for pct in (0.0, 0.5, 1, 2, 5, 10):
        tol = span * pct / 100
        cnt = core.removal_count(cum, tol)
        keep = np.setdiff1d(np.arange(len(co)), order[:cnt])
        # Apply for real with Blender and measure true deviation.
        import maya_graph_editor.common as common
        snap = common.CurveSnapshot.of(fc)
        snap.write(fc, keep=keep)
        xs2, ys2 = dense(fc)
        err = float(np.max(np.abs(ys2 - ys[: len(ys2)])))
        snap.write(fc)  # restore
        flag = "OK " if err <= tol * 1.25 + 1e-4 else "BAD"
        if flag == "BAD":
            ok = False
        print("   tol %5.1f%% (%.3f)  removed %3d/%d  -> true max error %.3f  %s"
              % (pct, tol, cnt, len(order), err, flag))
    return ok


if __name__ == "__main__":
    import types
    # stub package so `maya_graph_editor.common` imports without running register()
    sys.path.insert(0, os.path.join(HERE, ".."))
    ok = all([run_case("clamped", 'AUTO_CLAMPED'), run_case("auto", 'AUTO'),
              run_case("clamped", 'AUTO_CLAMPED', 'NONE'), run_case("auto", 'AUTO', 'NONE')])
    print("SIMPLIFY MODEL:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
