"""Headless tests for v1.2 (python tests/test_v12.py with a `bpy` Python)."""
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
from maya_graph_editor import cleanup, common, core, slider, smooth, tween, warp  # noqa: E402

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
                             show_header_tangents=False, use_theme_colors=True)
common.get_prefs = lambda: fake
addon.register()
scene = bpy.context.scene
st = scene.mge_settings
_curves = []
common.editable_fcurves = lambda context=None: list(_curves)
ctx = types.SimpleNamespace(area=types.SimpleNamespace(as_pointer=lambda: 1), scene=scene,
                            workspace=None, window=None)
check(set(core._registered) == set(common.TOOL_IDS), "all %d tools registered" % len(common.TOOL_IDS))


def run_slider(tool, value):
    """Drive a slider session like the modal does, without the UI."""
    jobs = tool.prepare(ctx)
    assert not isinstance(jobs, str), jobs
    slider._session = slider.Session(tool, ctx.area, jobs)
    slider.apply_value(ctx, value)
    return jobs


def end_slider(apply):
    ses = slider._session
    slider._session = None
    if not apply:
        fmap = common.fcurve_map(ctx)
        for j in ses.jobs:
            j.snap.write(fmap[j.key])


# ---------------------------------------------------------------------------
print("tween")
y = [0.0, 5.0, 7.0, 10.0]
sel = np.array([False, True, True, False])
check(np.allclose(tween.tween_values(y, sel, 50), [0, 5, 5, 10]), "50% -> halfway between neighbours")
check(np.allclose(tween.tween_values(y, sel, 0), [0, 0, 0, 10]), "0% -> previous key")
check(np.allclose(tween.tween_values(y, sel, 150), [0, 15, 15, 10]), "150% overshoots")
check(np.allclose(tween.tween_values(y, np.array([True, False, False, False]), 50), [5, 5, 7, 10]),
      "selection at the start uses the one neighbour it has")
f = make_curve([(1, 0), (5, 3), (9, 6), (13, 2)], obj_name="TW")
sel_only(f, [1, 2]); _curves[:] = [f]
before = [tuple(k.co) for k in f.keyframe_points]
run_slider(tween.TOOL, 25)
check([round(k.co[1], 4) for k in f.keyframe_points] == [0, 0.5, 0.5, 2], "live preview writes the curve")
slider.apply_value(ctx, 100)
check([round(k.co[1], 4) for k in f.keyframe_points] == [0, 2, 2, 2], "changing the value re-applies from the snapshot")
end_slider(apply=False)
check([tuple(k.co) for k in f.keyframe_points] == before, "cancel restores")
scene.frame_current = 3
sel_only(f, [])
f.select = True
tween.key_at_frame(f, 3.0, 50)
check(any(abs(k.co[0] - 3) < 1e-6 and abs(k.co[1] - 1.5) < 1e-6 for k in f.keyframe_points),
      "key at playhead halfway between frames 1 and 5")
sel_only(f, [])
check(tween.TOOL.prepare(ctx) == "Select keys that have unselected keys on at least one side",
      "nothing selected -> clear message")

# ---------------------------------------------------------------------------
print("smooth")
x = np.arange(0, 21, 1.0)
yy = np.where(x % 2 == 0, 1.0, -1.0)
s_all = np.ones(len(x), bool)
out = smooth.smooth_values(x, yy, s_all, 2.0)
check(np.abs(out[3:-3]).max() < 0.05, "alternating noise is flattened (max %.3f)" % np.abs(out[3:-3]).max())
check(out[0] == yy[0] and out[-1] == yy[-1], "run ends stay put")
check(np.allclose(smooth.smooth_values(x, yy, s_all, 0.0), yy), "blur 0 = no change")
lin = 2 * x + 1
check(np.allclose(smooth.smooth_values(x, lin, s_all, 3.0), lin, atol=1e-6),
      "a straight line stays straight, right up to the run ends")
fr = list(range(1, 31))
f = make_curve([(i, float(i % 2)) for i in fr], obj_name="SM")
select_all(f); _curves[:] = [f]
run_slider(smooth.TOOL, 3.0)
vals = [k.co[1] for k in f.keyframe_points]
check(max(vals[3:-3]) - min(vals[3:-3]) < 0.1, "live smooth on a real curve")
end_slider(apply=True)
check(abs(f.keyframe_points[10].co[1] - 0.5) < 0.1, "apply keeps the result")

# ---------------------------------------------------------------------------
print("time warp")
nx, k = warp.warp_times([0, 2.5, 5, 7.5, 10], 0, 10, 100, 'EASE_IN')
check(nx[0] == 0 and nx[-1] == 10 and nx[2] == 2.5, "ease in: ends fixed, middle key moves earlier (%.2f)" % nx[2])
check(all(np.diff(nx) > 0), "order kept")
nx2, _ = warp.warp_times([0, 2.5, 5, 7.5, 10], 0, 10, 0, 'EASE_IN')
check(np.allclose(nx2, [0, 2.5, 5, 7.5, 10]), "0% = unchanged")
nx3, _ = warp.warp_times([0, 2.5, 5, 7.5, 10], 0, 10, 100, 'EASE_IN_OUT')
check(abs(nx3[2] - 5) < 1e-9 and nx3[1] < 2.5 and nx3[3] > 7.5, "ease in/out is symmetric")
a = make_curve([(1, 0), (6, 2), (11, 5), (16, 3), (21, 0), (31, 1)], obj_name="WA")
sel_only(a, [0, 1, 2, 3, 4]); _curves[:] = [a]
st.warp_shape = 'EASE_OUT'
vals_before = [k.co[1] for k in a.keyframe_points]
run_slider(warp.TOOL, 100)
xs = [k.co[0] for k in a.keyframe_points]
check(xs[0] == 1 and xs[4] == 21 and xs[5] == 31, "range ends and keys outside unchanged: %s" % xs)
check(xs[1] > 6 and xs[2] > 11, "ease out pushes keys later: %s" % [round(v, 2) for v in xs])
check([k.co[1] for k in a.keyframe_points] == vals_before, "values never change")
end_slider(apply=False)

# ---------------------------------------------------------------------------
print("mocap cleanup")
fr = np.arange(1, 121)
noisy = np.sin(fr / 10.0) * 3 + np.random.default_rng(2).normal(0, 0.01, len(fr))
m = make_curve([(int(f), float(v)) for f, v in zip(fr[::3], noisy[::3])], obj_name="MC")
mod = m.modifiers.new('NOISE')
mod.strength = 5.0
select_all(m)
baked = cleanup.bake_selection(m)
check(baked == 118 and len(m.keyframe_points) == 118, "bake: one key per frame over the selection (%d)" % baked)
mod.mute = True
check(abs(m.evaluate(50.0) - np.interp(50, fr[::3], noisy[::3])) < 0.3, "baked without the modifier's noise")
mod.mute = False
m.modifiers.remove(mod)
select_all(m)
before, after = cleanup.cleanup_curve(m, bake=False, pct=1.0, tangent='CLAMPED')
check(after < before / 3, "simplified %d -> %d keys" % (before, after))
check(all(k.handle_left_type == 'AUTO_CLAMPED' for k in m.keyframe_points if k.select_control_point),
      "tangents applied")
_curves[:] = []

# ---------------------------------------------------------------------------
print("region lattice")
from maya_graph_editor import retime  # noqa: E402
r = make_curve([(1, 0), (11, 2), (21, 4), (31, 1), (41, 0)], obj_name="RG")
sel_only(r, [1, 2, 3])
snap = common.CurveSnapshot.of(r)
co, hl, hr = retime.transform_curve(snap, snap.selected, 11, 31, 11, 31,
                                    vbox=(1, 4, 1, 7), mapping=(1.0, 0.0))
check(np.allclose(co[1:4, 1], [3, 7, 1]), "top edge x2 about the bottom edge: %s" % co[1:4, 1])
check(np.allclose(co[[0, 4], 1], [0, 0]), "unselected values untouched")
check(np.allclose(hr[1:4, 1] - co[1:4, 1], (snap.hr[1:4, 1] - snap.co[1:4, 1]) * 2),
      "handle heights scale with the values")
deg = 180 / np.pi
co, _, _ = retime.transform_curve(snap, snap.selected, 11, 31, 11, 31,
                                  vbox=(1 * deg, 4 * deg, 1 * deg, 7 * deg), mapping=(deg, 0.0))
check(np.allclose(co[1:4, 1], [3, 7, 1]), "same result for a curve shown in degrees")
co, _, _ = retime.transform_curve(snap, snap.selected, 11, 31, 16, 36, ripple_after=True,
                                  vbox=(1, 4, 2, 5), mapping=(1.0, 0.0))
check(list(co[:, 0]) == [1, 16, 26, 36, 46] and np.allclose(co[1:4, 1], [3, 5, 2]),
      "move +5 frames / +1 value, later key rippled: %s" % list(co[:, 0]))
co, _, _ = retime.scale_values(snap, snap.selected, 50, 'ZERO')
check(np.allclose(co[1:4, 1], [1, 2, 0.5]), "value 50% about zero")
co, _, _ = retime.scale_values(snap, snap.selected, 200, 'FIRST')
check(np.allclose(co[1:4, 1], [2, 6, 0]), "value 200% about the first key")
co, _, _ = retime.scale_values(snap, snap.selected, 0, 'CENTER')
check(np.allclose(co[1:4, 1], [2.5, 2.5, 2.5]), "value 0% about the centre flattens")
check(retime.scaled_range(10, 20, 200, 'PLAYHEAD', 0) == (20, 40), "anchor at the playhead")

ses = retime.Session(types.SimpleNamespace(as_pointer=lambda: 1))
ses.values = True
check(retime.hit_test(ses, 100, 50, 100, 300, 50, 200) == 'BL', "corner hit")
check(retime.hit_test(ses, 200, 200, 100, 300, 50, 200) == 'T', "top edge hit")
check(retime.hit_test(ses, 300, 500, 100, 300, 50, 200) == 'R', "time edge hit anywhere vertically")
check(retime.hit_test(ses, 200, 120, 100, 300, 50, 200) == 'M', "inside -> move")
check(retime.hit_test(ses, 500, 120, 100, 300, 50, 200) is None, "outside -> nothing")

_curves[:] = [r]
st.retime_scope = 'SELECTED'
st.retime_ripple = False
check(retime.retime_to(ctx, 11.0, 51.0) == (11.0, 51.0), "retime_to an exact range")
check([round(k.co[0], 3) for k in r.keyframe_points] == [1, 11, 31, 41, 51],
      "keys spread to 11..51 (no ripple: passes the later key, Blender re-sorts): %s" % [round(k.co[0], 3) for k in r.keyframe_points])

# whole rig: hidden channels move too
rigobj_curves = [make_curve([(1, 0), (10, 1), (20, 2), (30, 3)], obj_name="RIG", path="location", index=i)
                 for i in range(3)]
for fc in rigobj_curves:
    sel_only(fc, [])
sel_only(rigobj_curves[0], [1, 2])          # selection only on X
_curves[:] = [rigobj_curves[0]]            # only X is shown in the editor
rig_obj = bpy.data.objects["RIG"]
rig_ctx = types.SimpleNamespace(area=ctx.area, scene=scene, selected_objects=[rig_obj],
                                active_object=rig_obj, selected_pose_bones=None)
st.retime_scope = 'RIG'
st.retime_ripple = True
res = retime.scale_selection(rig_ctx, 200, 'LEFT')
xs = [[k.co[0] for k in fc.keyframe_points] for fc in rigobj_curves]
check(res == (10, 30) and all(x == [1, 10, 30, 40] for x in xs),
      "whole rig: hidden Y/Z channels retimed with X: %s" % xs)
st.retime_scope = 'SELECTED'
_curves[:] = []

# ---------------------------------------------------------------------------
print("theme colours")
cols = common.ui_colors()
check(set(cols) == {"bg", "text", "dim", "track", "accent", "active"} and all(len(c) == 4 for c in cols.values()),
      "theme colours resolved")
fake.use_theme_colors = False
check(common.ui_colors() == common._FIXED, "fixed colours when the preference is off")

# ---------------------------------------------------------------------------
print("translations / extension platform")
from maya_graph_editor import i18n, updater  # noqa: E402
tr = i18n.build()
check(tr["ru_RU"][("*", "Snapshot")] == "Снимок" and tr["es"][("Operator", "Snapshot")] == "Captura",
      "translation tables built for ru_RU and es")
check(set(tr) >= {"ru_RU", "es", "fr_FR", "de_DE", "ja_JP", "zh_HANS", "zh_CN", "pt_BR"},
      "seven languages (plus the older Chinese locale name)")
missing = {loc: sum(1 for row in i18n.TABLE.values() if not row[i]) for i, loc in enumerate(i18n.LOCALES)}
check(all(v == 0 for v in missing.values()), "no untranslated strings: %s" % missing)
bad = [en for en, row in i18n.TABLE.items() if "{" in en and
       any(sorted(__import__("re").findall(r"{\w+}", t)) != sorted(__import__("re").findall(r"{\w+}", en)) for t in row)]
check(not bad, "format placeholders intact in every language %s" % bad)
check(all(len(row) == len(i18n.LOCALES) for row in i18n.TABLE.values()), "every string has every language")
prefs = bpy.context.preferences
old_lang = (prefs.view.language, prefs.view.use_translate_interface)
try:
    prefs.view.language = 'ru_RU'
    prefs.view.use_translate_interface = True
    got = bpy.app.translations.pgettext_iface("Snapshot")
    check(got == "Снимок", "Blender returns the Russian label (%s)" % got)
except Exception as e:
    print("  (language switch unavailable here: %s)" % e)
finally:
    prefs.view.language, prefs.view.use_translate_interface = old_lang
check(updater.managed_by_blender() is None, "not managed by a remote repo in this install")
updater.common.PKG = "bl_ext.blender_org.maya_graph_editor"
fake_repo = types.SimpleNamespace(module="blender_org", use_remote_url=True, name="extensions.blender.org",
                                  remote_url="https://extensions.blender.org/api/v1/extensions/")
real_prefs = bpy.context.preferences
import maya_graph_editor.updater as up_mod  # noqa: E402
orig_ctx = up_mod.bpy
up_mod.bpy = types.SimpleNamespace(context=types.SimpleNamespace(
    preferences=types.SimpleNamespace(extensions=types.SimpleNamespace(repos=[fake_repo]))), app=bpy.app)
check(updater.managed_by_blender() == "extensions.blender.org", "installed from extensions.blender.org -> updater off")
up_mod.bpy = orig_ctx
updater.common.PKG = "maya_graph_editor"

addon.unregister()
print()
print("FAILURES: %d" % len(FAILS))
for msg in FAILS:
    print("  -", msg)
sys.exit(1 if FAILS else 0)
