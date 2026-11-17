"""Headless tests for v1.3 (python tests/test_v13.py with a `bpy` Python)."""
import json
import os
import sys
import tempfile
import types

import numpy as np
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from bpy_helpers import all_fcurves, make_curve, select_all  # noqa: E402

import maya_graph_editor as addon  # noqa: E402
from maya_graph_editor import (blocking, channels, common, core, curves, generate, ghost,  # noqa: E402
                               presets, shapes, slider, stacked, stagger, whatsnew)

FAILS = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def sel_only(fc, idx):
    for i, k in enumerate(fc.keyframe_points):
        on = i in idx
        k.select_control_point = k.select_left_handle = k.select_right_handle = on


def xs_of(fc):
    return [round(k.co[0], 3) for k in fc.keyframe_points]


def ys_of(fc):
    return [round(k.co[1], 3) for k in fc.keyframe_points]


fake = types.SimpleNamespace(**{"enable_" + n: True for n in common.TOOL_IDS},
                             show_header_tangents=False, use_theme_colors=True, hud_scale=1.0,
                             last_seen_version="", show_whats_new=True)
common.get_prefs = lambda: fake
addon.register()
scene = bpy.context.scene
st = scene.mge_settings
_curves = []
common.editable_fcurves = lambda context=None: list(_curves)
common.visible_fcurves = lambda context=None: list(_curves)
ctx = types.SimpleNamespace(area=types.SimpleNamespace(as_pointer=lambda: 1), scene=scene,
                            workspace=None, window=None)
check(set(core._registered) == set(common.TOOL_IDS), "all %d tools registered" % len(common.TOOL_IDS))


def run_slider(tool, value):
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
print("blocking: stepped preview")
f = make_curve([(1, 0), (10, 5), (20, 1)], obj_name="BL")
f.keyframe_points[1].interpolation = 'LINEAR'
orig = [k.interpolation for k in f.keyframe_points]
blocking.stepped_on([f])
check(all(k.interpolation == 'CONSTANT' for k in f.keyframe_points) and blocking.stepped_active([f]),
      "on: every key constant, state stored on the action")
f.keyframe_points.insert(15, 3.0)
path = os.path.join(tempfile.mkdtemp(), "stepped.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.wm.open_mainfile(filepath=path)
scene = bpy.context.scene
st = scene.mge_settings
ctx.scene = scene
f = all_fcurves(bpy.data.objects["BL"].animation_data.action)[0]
check(blocking.stepped_active([f]), "state survives save and reopen")
blocking.stepped_off([f])
got = {round(k.co[0]): k.interpolation for k in f.keyframe_points}
check(got[1] == orig[0] and got[10] == 'LINEAR' and got[20] == orig[2], "off: original interpolation back: %s" % got)
check(got[15] == bpy.context.preferences.edit.keyframe_new_interpolation_type,
      "a key added during the preview gets the default interpolation")
check(not blocking.stepped_active([f]), "state removed")

print("blocking: round, loop, equalize")
f = make_curve([(1.3, 0), (9.6, 5), (10.4, 2), (20.5, 1)], obj_name="RD")
select_all(f)
h = f.keyframe_points[0].handle_right[0] - f.keyframe_points[0].co[0]
moved = blocking.round_keys(f)
check(xs_of(f) == [1.0, 10.0, 20.0] or xs_of(f) == [1.0, 10.0, 21.0] or len(xs_of(f)) == 3,
      "rounded to whole frames, duplicates merged: %s (moved %d)" % (xs_of(f), moved))
check(all(float(x).is_integer() for x in xs_of(f)), "every key on a whole frame")
f = make_curve([(1, 2), (10, 5), (20, 0)], obj_name="LP")
blocking.seamless_loop(f)
check(ys_of(f)[-1] == 2.0 and curves.get_infinity(f, 'POST') == 'CYCLE' and curves.get_infinity(f, 'PRE') == 'CYCLE',
      "loop: last key matches the first, cycle on both sides")
check(abs(f.evaluate(20.0) - f.evaluate(1.0)) < 1e-5 and abs(f.evaluate(25.0) - f.evaluate(6.0)) < 1e-4,
      "curve repeats")
eps = 0.01
s_end = (f.evaluate(20.0) - f.evaluate(20.0 - eps)) / eps
s_start = (f.evaluate(1.0 + eps) - f.evaluate(1.0)) / eps
check(abs(s_end - s_start) < 0.05, "no kink at the loop point (slopes %.3f / %.3f)" % (s_end, s_start))
f = make_curve([(1, 0), (10, 5), (40, 1)], obj_name="EQ", handle='FREE')
k = f.keyframe_points[1]
k.handle_left = (9.0, 4.0); k.handle_right = (11.0, 7.0); f.update()
sel_only(f, [1])
blocking.equalize_handles(f)
k = f.keyframe_points[1]
check(abs(k.co[0] - k.handle_left[0] - 3.0) < 1e-4 and abs(k.handle_right[0] - k.co[0] - 10.0) < 1e-4,
      "handle lengths = a third of each neighbouring segment")
check(abs((k.co[1] - k.handle_left[1]) / 3.0 - 1.0) < 1e-4 and abs((k.handle_right[1] - k.co[1]) / 10.0 - 2.0) < 1e-4,
      "angles kept")

# ---------------------------------------------------------------------------
print("stagger / overlap")
arm = bpy.data.armatures.new("Arm")
rig = bpy.data.objects.new("Rig", arm)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')
prev = None
for i, name in enumerate(("root", "mid", "tip")):
    b = arm.edit_bones.new(name)
    b.head, b.tail = (0, i, 0), (0, i + 1, 0)
    b.parent = prev
    prev = b
bpy.ops.object.mode_set(mode='POSE')
for name in ("tip", "root", "mid"):       # keyed in a scrambled order on purpose
    pb = rig.pose.bones[name]
    pb.rotation_mode = 'XYZ'
    for fr, v in ((1, 0.0), (11, 1.0), (21, 0.0)):
        pb.rotation_euler[0] = v
        pb.keyframe_insert("rotation_euler", index=0, frame=fr)
bpy.ops.object.mode_set(mode='OBJECT')
bone_curves = {fc.data_path.split('"')[1]: fc for fc in all_fcurves(rig.animation_data.action)}
ordered = [bone_curves[n] for n in ("tip", "root", "mid")]
groups = stagger.build_groups(ordered, 'BONE', 'HIERARCHY')
check([g[0].data_path.split('"')[1] for g in groups] == ["root", "mid", "tip"], "hierarchy order root -> tip")
groups = stagger.build_groups(ordered, 'BONE', 'CHANNEL', reverse=True)
check([g[0].data_path.split('"')[1] for g in groups] == ["mid", "root", "tip"], "channel order, reversed")
for fc in ordered:
    select_all(fc)
_curves[:] = ordered
st.stagger_group, st.stagger_order, st.stagger_reverse, st.stagger_gain = 'BONE', 'HIERARCHY', False, 50.0
run_slider(stagger.STAGGER, 3.0)
check(xs_of(bone_curves["root"]) == [1, 11, 21] and xs_of(bone_curves["mid"]) == [4, 14, 24]
      and xs_of(bone_curves["tip"]) == [7, 17, 27], "each bone 3 frames later than its parent")
check(ys_of(bone_curves["mid"])[1] == 0.5 and ys_of(bone_curves["tip"])[1] == 0.25, "gain 50% per step")
end_slider(apply=False)
check(xs_of(bone_curves["tip"]) == [1, 11, 21] and ys_of(bone_curves["tip"])[1] == 1.0, "cancel restores")

# overlap: followers have different animation; leader is root
for fc in (bone_curves["mid"], bone_curves["tip"]):
    fc.keyframe_points[1].co[1] = 9.0
    fc.keyframe_points[0].co[1] = 0.2
    fc.update()
    sel_only(fc, [])
    fc.select = True
select_all(bone_curves["root"])
st.overlap_gain = 50.0
run_slider(stagger.OVERLAP, 2.0)
check(xs_of(bone_curves["mid"]) == [3, 13, 23] and xs_of(bone_curves["tip"]) == [5, 15, 25],
      "followers get the leader's keys, 2 frames later each")
check(ys_of(bone_curves["mid"]) == [0.2, 0.7, 0.2] and ys_of(bone_curves["tip"]) == [0.2, 0.45, 0.2],
      "scaled copies from each follower's own start value: %s %s"
      % (ys_of(bone_curves["mid"]), ys_of(bone_curves["tip"])))
check(xs_of(bone_curves["root"]) == [1, 11, 21], "leader untouched")
end_slider(apply=False)
check(ys_of(bone_curves["mid"])[1] == 9.0, "cancel restores the followers")
_curves[:] = []

# ---------------------------------------------------------------------------
print("channels")
obj_curves = [make_curve([(1, 0), (10, 1), (20, 2)], obj_name="CH", path=p, index=i)
              for p in ("location", "rotation_euler") for i in range(3)]
ch = bpy.data.objects["CH"]
cctx = types.SimpleNamespace(selected_objects=[ch], active_object=ch)
check(len(channels.object_fcurves(cctx)) == 6, "all six curves of the object found")
members = channels.set_from_curves(obj_curves[3:])
check(channels.apply_set(obj_curves, members) == 3 and [fc.hide for fc in obj_curves] == [True] * 3 + [False] * 3,
      "applying a set shows only its channels")
members_json = json.loads(json.dumps(members))
check(channels.apply_set(obj_curves, members_json) == 3, "a set read back from JSON still matches")
channels.show_all(obj_curves)
check(not any(fc.hide for fc in obj_curves), "show all")
obj_curves[0].hide = True
picked = {common.curve_key(obj_curves[4])}
check(channels.isolate_toggle(obj_curves, picked) and [fc.hide for fc in obj_curves] == [True] * 4 + [False, True],
      "isolate shows only the picked curve")
check(not channels.isolate_toggle(obj_curves, set()) and [fc.hide for fc in obj_curves] == [True] + [False] * 5,
      "second click restores exactly what was visible before")
obj_curves[0].hide = False
scene.frame_current = 10
check(channels.select_keys(obj_curves, 'PLAYHEAD', scene) == 6, "select keys at the playhead on every curve")
scene.use_preview_range, scene.frame_preview_start, scene.frame_preview_end = True, 5, 25
check(channels.select_keys(obj_curves, 'PREVIEW', scene) == 12, "select keys in the preview range")
scene.use_preview_range = False
sel_only(obj_curves[0], [0, 1])
sel_only(obj_curves[1], [])
channels.select_keys(obj_curves[:2], 'INVERT', scene)
check([k.select_control_point for k in obj_curves[0].keyframe_points] == [False, False, True]
      and not any(k.select_control_point for k in obj_curves[1].keyframe_points),
      "invert only on curves that had a selection")
long = make_curve([(i, i) for i in range(1, 11)], obj_name="NTH")
select_all(long)
channels.select_keys([long], 'NTH', scene, nth=3)
check([i for i, k in enumerate(long.keyframe_points) if k.select_control_point] == [0, 3, 6, 9], "every 3rd key")


# ---------------------------------------------------------------------------
print("ghost: from another action, swap range, palette")
ref = make_curve([(1, 0), (10, 8), (20, 0)], obj_name="REF")
tgt = make_curve([(1, 0), (10, 2), (20, 0), (30, 4)], obj_name="TGT")
n = ghost.snapshot_from_action([tgt], ref.id_data, 'A', scene, st)
buf = ghost._buffers.get(('A', common.curve_key(tgt)))
check(n == 1 and buf is not None and abs(buf.samples[:, 1].max() - 8) < 0.01,
      "ghost of the target shows the reference action's curve")
ghost.clear_buffers()
ghost.take_snapshot([tgt], 'A', scene, st)
tgt.keyframe_points[1].co[1] = 6.0
tgt.keyframe_points[3].co[1] = 9.0
tgt.update()
sel_only(tgt, [0, 1, 2])
ghost.swap_range_with_buffer([tgt], 'A')
check(ys_of(tgt) == [0, 2, 0, 9], "swap range: selected range back to the ghost, the rest kept: %s" % ys_of(tgt))
buf = ghost._buffers[('A', common.curve_key(tgt))]
check([round(v, 3) for v in buf.keys.co[:, 1]] == [0, 6, 0, 4], "ghost now holds the edited range")
ghost.clear_buffers()
check(len(ghost.PALETTES['CB_SAFE']) == 3 and ghost.PALETTES['CB_SAFE'] != ghost.PALETTES['DEFAULT'],
      "colour-blind-safe palette defined")

# ---------------------------------------------------------------------------
print("noise / settle")
x = np.arange(0, 50.0)
check(np.array_equal(generate.smooth_noise(x / 6, 5), generate.smooth_noise(x / 6, 5)), "same seed, same noise")
check(not np.allclose(generate.smooth_noise(x / 6, 5), generate.smooth_noise(x / 6, 6)), "different seed differs")
nz = generate.smooth_noise(np.linspace(0, 40, 2000), 3)
check(np.abs(nz).max() <= 1.0 and np.abs(np.diff(nz)).max() < 0.05, "noise is bounded and smooth")
y = np.linspace(0, 10, 50)
sel = np.ones(50, bool); sel[:5] = False
out = generate.noise_values(x, y, sel, 10.0, 6.0, 1)
check(np.array_equal(out[:5], y[:5]) and np.abs(out[5:] - y[5:]).max() <= 0.1 * (y[5:].max() - y[5:].min()) + 1e-9
      and np.abs(out[5:] - y[5:]).max() > 0.05, "amount is a share of the value range; unselected untouched")
sc = make_curve([(1, 0), (11, 10), (60, 10)], obj_name="SE")
sel_only(sc, [1])
snap = common.CurveSnapshot.of(sc)
res = generate.settle_snapshot(snap, 100.0, 8.0, 24.0)
ys = res.co[:, 1]
xs = res.co[:, 0]
after = (xs > 11) & (xs <= 35)
check(after.sum() >= 8 and xs[-1] == 60, "settle keys added after the selected key, later key kept")
check(ys[after][0] > 10 and ys[after].min() < 10, "overshoots in the direction of travel, then swings back")
amp = np.abs(ys[after] - 10)
check(amp[-1] == 0 and amp[:3].max() > amp[-4:].max(), "wobble dies down and ends at rest")
check(generate.settle_snapshot(snap, 0.0, 8, 24) is snap, "0% = no change")

# ---------------------------------------------------------------------------
print("shape library / paste")
real_path = shapes.library_path
tmp_lib = os.path.join(tempfile.mkdtemp(), "shapes.json")
shapes.library_path = lambda: tmp_lib
sh = make_curve([(1, 0), (5, 6), (9, 4)], obj_name="SH")
select_all(sh)
shape = shapes.shape_from_snapshot(common.CurveSnapshot.of(sh))
check(shape["anchored"] and [round(k["u"], 3) for k in shape["keys"]] == [0, 0.5, 1]
      and [round(k["v"], 3) for k in shape["keys"]] == [0, 1.5, 1], "shape normalised in time and value")
shapes.save_user_shapes({"Mine": shape})
check("Mine" in shapes.all_shapes() and "Overshoot" in shapes.all_shapes(), "library holds built-in and saved shapes")
check([i[0] for i in shapes.enum_items()][-1] == "Mine", "shape list for the dropdown")
t = make_curve([(10, 2), (20, 3), (30, 12), (50, 0)], obj_name="SHT")
sel_only(t, [0, 1, 2])
shapes.apply_shape(t, shapes.all_shapes()["Mine"])
check(xs_of(t) == [10, 20, 30, 50] and ys_of(t) == [2, 17, 12, 0],
      "saved shape stretched between the first and last selected key: %s" % ys_of(t))
sel_only(t, [0, 2])
shapes.apply_shape(t, shapes.BUILTIN["Overshoot"])
check(xs_of(t) == [10, 24, 30, 50] and abs(ys_of(t)[1] - (2 + 1.12 * 10)) < 1e-3, "built-in Overshoot applied")
shapes.library_path = real_path

src = make_curve([(1, 0), (5, 4), (9, 2)], obj_name="CP")
select_all(src)
check(shapes.copy_keys([src]) == 1 and shapes.clipboard_size() == 1, "copy")
def target():
    f2 = make_curve([(1, 1), (22, 1), (40, 1)], obj_name="CPT")
    for k in f2.keyframe_points:
        k.co[1] = 1.0
    f2.update()
    sel_only(f2, [])
    return f2
t = target(); shapes.paste_curve(t, shapes._source_for(t), 'MERGE', 20)
check(xs_of(t) == [1, 20, 22, 24, 28, 40], "merge keeps existing keys: %s" % xs_of(t))
bpy.data.objects.remove(bpy.data.objects["CPT"])
t = target(); shapes.paste_curve(t, shapes._source_for(t), 'REPLACE', 20)
check(xs_of(t) == [1, 20, 24, 28, 40], "replace removes keys in the pasted range: %s" % xs_of(t))
bpy.data.objects.remove(bpy.data.objects["CPT"])
t = target(); shapes.paste_curve(t, shapes._source_for(t), 'INSERT', 20)
check(xs_of(t) == [1, 20, 24, 28, 30, 48], "insert pushes later keys back by the pasted length: %s" % xs_of(t))
bpy.data.objects.remove(bpy.data.objects["CPT"])
t = target(); sel_only(t, [0, 2]); shapes.paste_curve(t, shapes._source_for(t), 'FIT', 20)
check(xs_of(t) == [1, 20.5, 40], "fit stretches the copied keys over the selected range: %s" % xs_of(t))
bpy.data.objects.remove(bpy.data.objects["CPT"])
t = target(); shapes.paste_curve(t, shapes._source_for(t), 'REPLACE', 20, relative=True)
check(ys_of(t)[1:4] == [1, 5, 3], "relative values start from the curve's own value: %s" % ys_of(t))

# ---------------------------------------------------------------------------
print("stacked overview")
lanes = stacked.lane_layout(4, 400)
check(len(lanes) == 4 and lanes[0][1] > lanes[1][1] and all(hi > lo for lo, hi in lanes), "lanes stacked top to bottom")
check(len(stacked.lane_layout(100, 400)) == stacked.MAX_LANES, "lane count capped")
pts = stacked.lane_points([0, 1, 2], [5, 10, 7], [0, 50, 100], 100, 200)
check(min(p[1] for p in pts) > 100 and max(p[1] for p in pts) < 200, "curve scaled inside its lane")
check(stacked.channel_label(bone_curves["tip"]) == "tip  rotation_euler X", "lane label: %s"
      % stacked.channel_label(bone_curves["tip"]))

# ---------------------------------------------------------------------------
print("NLA time mapping")
nl = make_curve([(1, 0), (11, 5)], obj_name="NLA")
nobj = bpy.data.objects["NLA"]
check(common.nla_mapping(nl) == (1.0, 0.0), "identity outside tweak mode")
ad = nobj.animation_data
act = ad.action
track = ad.nla_tracks.new()
strip = track.strips.new("s", 50, act)
strip.scale = 2.0
ad.action = None
strip.select = True
track.select = True
ad.nla_tracks.active = track
ad.use_tweak_mode = True
common.clear_caches()
nl = all_fcurves(ad.action)[0]
scale, off = common.nla_mapping(nl)
check(abs(scale * 1 + off - ad.nla_tweak_strip_time_to_scene(1.0)) < 1e-4
      and abs(scale * 11 + off - ad.nla_tweak_strip_time_to_scene(11.0)) < 1e-4 and abs(scale - 2.0) < 1e-4,
      "tweak mode: keys map to strip time (scale %.1f, offset %.1f)" % (scale, off))
ad.use_tweak_mode = False

# ---------------------------------------------------------------------------
print("what's new / settings export")
check(whatsnew.pending("1.2.1", (1, 3, 0)) == [(1, 3, 0)], "notes pending after updating from 1.2.1")
check(whatsnew.pending("1.1.0", (1, 3, 0)) == [(1, 3, 0), (1, 2, 0)], "skipped versions are included")
check(whatsnew.pending("1.3.0", (1, 3, 0)) == [], "nothing when already seen")
cur = ".".join(str(v) for v in whatsnew.current_version())
fake.last_seen_version = ""
whatsnew.remember_first_install()
check(fake.last_seen_version == cur and not whatsnew.notice_pending(), "first install: nothing to announce")
fake.last_seen_version = "1.2.1"
check(whatsnew.notice_pending(), "after an update: a note in the Maya tab (no popup, no timer)")
fake.show_whats_new = False
check(not whatsnew.notice_pending(), "the note can be switched off")
fake.show_whats_new = True
fake.last_seen_version = cur
st.tween_bias, st.ghost_style, st.stagger_gain = 75.0, 'DASHED', 80.0
item = st.channel_sets.add(); item.name, item.data = "arms", json.dumps([["location", 0]])
real_dump = presets._dump
data = presets.export_dict(types.SimpleNamespace(scene=scene))
blob = json.dumps(data)
check(data["settings"]["tween_bias"] == 75.0 and data["settings"]["ghost_style"] == 'DASHED'
      and len(data["settings"]["ghost_color_a"]) == 4 and data["channel_sets"][0]["name"] == "arms",
      "export holds tool settings, colours and channel sets (%d bytes of JSON)" % len(blob))
st.tween_bias, st.ghost_style, st.stagger_gain = 50.0, 'SOLID', 100.0
st.channel_sets.clear()
n = presets.import_dict(types.SimpleNamespace(scene=scene), json.loads(blob))
check(st.tween_bias == 75.0 and st.ghost_style == 'DASHED' and st.stagger_gain == 80.0
      and len(st.channel_sets) == 1 and n > 20, "import restores them (%d values)" % n)
try:
    presets.import_dict(types.SimpleNamespace(scene=scene), {"something": "else"})
    check(False, "foreign file rejected")
except ValueError:
    check(True, "foreign file rejected")

# ---------------------------------------------------------------------------
print("no background timers")
import re as _re  # noqa: E402
src_dir = os.path.join(HERE, "..", "maya_graph_editor")
timer_lines = []
for fn in sorted(os.listdir(src_dir)):
    if fn.endswith(".py"):
        for ln in open(os.path.join(src_dir, fn), encoding="utf-8"):
            if _re.search(r"bpy\.app\.timers\.register", ln):
                timer_lines.append(fn)
check(timer_lines == ["updater.py"], "only the updater (GitHub build, while a check runs) uses a timer: %s"
      % timer_lines)
check("auto_frame" not in scene.mge_settings.bl_rna.properties and not hasattr(channels, "_auto_frame_tick"),
      "auto frame removed")

addon.unregister()
print()
print("FAILURES: %d" % len(FAILS))
for msg in FAILS:
    print("  -", msg)
sys.exit(1 if FAILS else 0)
