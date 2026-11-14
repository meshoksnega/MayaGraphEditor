"""Real-GUI tests: run inside a windowed Blender with simulated events.

    xvfb-run -a -s "-screen 0 1600x1000x24" blender --factory-startup \\
        --enable-event-simulate --python tests/gui/run_gui_tests.py

Needs the add-on installed as a legacy add-on named ``maya_graph_editor``
(the CI workflow links it into BLENDER_USER_SCRIPTS/addons).  Writes
screenshots to $MGE_SHOTS (default: ./gui_shots) and exits non-zero on any
failure or Python traceback.
"""

import io
import os
import sys
import traceback

import bpy
import addon_utils

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bpy_helpers import make_curve, select_all  # noqa: E402

SHOTS = os.environ.get("MGE_SHOTS", os.path.join(os.getcwd(), "gui_shots"))
os.makedirs(SHOTS, exist_ok=True)
FAILS = []
ERRORS = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


class Tee(io.TextIOBase):
    """Copy stderr and remember Python tracebacks printed by Blender."""

    def __init__(self, real):
        self.real = real

    def write(self, s):
        if "Traceback" in s or "Error:" in s:
            ERRORS.append(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()


sys.stderr = Tee(sys.stderr)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def win():
    return bpy.context.window_manager.windows[0]


def graph_area():
    return next(a for a in win().screen.areas if a.type == 'GRAPH_EDITOR')


def region_of(area, kind):
    return next(r for r in area.regions if r.type == kind)


def override(region_kind='WINDOW'):
    area = graph_area()
    return bpy.context.temp_override(window=win(), area=area,
                                     region=region_of(area, region_kind))


def ev(type_, value='PRESS', x=None, y=None, **mods):
    w = win()
    if x is None:
        r = region_of(graph_area(), 'WINDOW')
        x, y = r.x + r.width // 2, r.y + r.height // 2
    w.event_simulate(type=type_, value=value, x=int(x), y=int(y), **mods)


def key(type_, **mods):
    ev(type_, 'PRESS', **mods)
    ev(type_, 'RELEASE', **mods)


def redraw():
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)


def shot(name, area_only=True):
    """Grab the X display (Blender's own screenshot is blank under Xvfb).

    Saves <version>_<name>.png cropped to the Graph Editor (or the whole window)."""
    import subprocess
    redraw()
    path = os.path.join(SHOTS, "%s_%s.png" % (bpy.app.version_string.split()[0], name))
    w = win()
    geom = []
    if area_only:
        a = graph_area()
        top = w.height - (a.y + a.height)  # X origin is top-left
        geom = ["-crop", "%dx%d+%d+%d" % (a.width, a.height, a.x, top)]
    try:
        subprocess.run(["import", "-silent", "-window", "root"] + geom + [path],
                       check=True, timeout=20)
        print("  screenshot", path, flush=True)
    except Exception as e:
        print("  (screenshot failed: %s)" % e, flush=True)


def frame_to_px(frame):
    r = region_of(graph_area(), 'WINDOW')
    x, _y = r.view2d.view_to_region(frame, 0, clip=False)
    return r.x + x


def keys_of(fc):
    return [tuple(round(v, 4) for v in k.co) for k in fc.keyframe_points]


def view_all():
    with override():
        bpy.ops.graph.view_all()


# --------------------------------------------------------------------------
# the test sequence (a generator: each yield lets Blender process events)
# --------------------------------------------------------------------------

def sequence():
    print("Blender", bpy.app.version_string, flush=True)
    # close the splash screen so it doesn't cover the screenshots
    bpy.context.preferences.view.show_splash = False
    yield 0.5
    w = win()
    ev('ESC', 'PRESS', 5, 5)
    ev('ESC', 'RELEASE', 5, 5)
    ev('LEFTMOUSE', 'PRESS', 5, w.height - 5)
    ev('LEFTMOUSE', 'RELEASE', 5, w.height - 5)
    yield 0.3
    mod = addon_utils.enable("maya_graph_editor", default_set=True)
    check(mod is not None, "add-on enabled")
    yield 0.2
    from maya_graph_editor import common, ghost, retime, simplify, keymaps, slider  # noqa: F401
    logged = []
    real_log = common.log_exception

    def log(where):
        logged.append(where)
        real_log(where)
    common.log_exception = log

    # Big area -> Graph Editor with the sidebar open on the Maya tab
    screen = win().screen
    area = max(screen.areas, key=lambda a: a.width * a.height)
    area.type = 'GRAPH_EDITOR'
    area.ui_type = 'FCURVES'
    area.spaces.active.show_region_ui = True
    yield 0.3
    ui = region_of(graph_area(), 'UI')
    try:
        ui.active_panel_category = "Maya"
        check(True, "sidebar switched to the Maya tab")
    except Exception as e:
        print("  (cannot switch sidebar tab: %s)" % e)

    # Shortcut conflicts with Blender's default Graph Editor keymap
    kc = bpy.context.window_manager.keyconfigs.default
    km = kc.keymaps.get("Graph Editor")
    ours = {(d[1], d[2], d[3], d[4]) for items in keymaps.DEFAULTS.values() for d in items}
    clashes = []
    for kmi in km.keymap_items:
        sig = (kmi.type, kmi.ctrl == 1, kmi.shift == 1, kmi.alt == 1)
        if sig in ours and kmi.active and not kmi.oskey:
            clashes.append("%s -> %s" % (sig, kmi.idname))
    check(not clashes, "no clash with default Graph Editor shortcuts %s" % clashes)

    # Animation on the default cube
    obj = bpy.data.objects.get("Cube") or bpy.context.active_object
    obj_name = obj.name
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    pts = [(f, ((f * 7) % 11) / 3.0) for f in range(1, 41, 3)]
    fc = make_curve(pts, obj_name=obj.name, path="location", index=2)
    select_all(fc)
    view_all()
    yield 0.3
    redraw()
    shot("01_curve")
    r = region_of(graph_area(), 'WINDOW')
    ox, oy, sx, sy = common.view_affine(r)
    worst = 0.0
    for fx, vy in ((1, 0.0), (20, 1.5), (40, 3.0), (-30, -2.0), (90, 5.0)):
        px, py = r.view2d.view_to_region(fx, vy, clip=False)
        worst = max(worst, abs(ox + fx * sx - px), abs(oy + vy * sy - py))
    check(worst <= 1.0, "overlay mapping matches Blender's view within 1 px (worst %.2f px)" % worst)

    # ---------------------------------------------------------- ghost
    print("ghost", flush=True)
    calls = {"poly": 0, "seg": 0}
    real_poly, real_seg = common.draw_polyline, common.draw_segments

    def poly(*a, **k):
        calls["poly"] += 1
        return real_poly(*a, **k)

    def seg(*a, **k):
        calls["seg"] += 1
        return real_seg(*a, **k)
    common.draw_polyline, common.draw_segments = poly, seg
    with override():
        res = bpy.ops.mge.ghost_snapshot()
    check(res == {'FINISHED'} and ghost.buffer_count() == 1, "snapshot from the Graph Editor")
    for k in fc.keyframe_points[3:7]:
        k.co[1] += 1.5
        k.handle_left[1] += 1.5
        k.handle_right[1] += 1.5
    fc.update()
    yield 0.2
    redraw()
    yield 0.1
    check(calls["poly"] > 0, "ghost draw handler drew (%d polylines)" % calls["poly"])
    shot("02_ghost")
    bpy.context.scene.mge_settings.ghost_style = 'DASHED'
    redraw()
    yield 0.1
    check(calls["seg"] > 0, "dashed ghost drew")
    shot("03_ghost_dashed")
    with override():
        bpy.ops.mge.ghost_swap()
    check(abs(fc.keyframe_points[4].co[1] - pts[4][1]) < 1e-4, "swap restored the buffered keys")
    with override():
        bpy.ops.mge.ghost_clear(slot='ALL')

    # ---------------------------------------------------------- tangents
    print("tangents", flush=True)
    with override('UI'):
        res = bpy.ops.mge.set_tangent(kind='STEPPED', side='BOTH')
    check(res == {'FINISHED'} and all(k.interpolation == 'CONSTANT' for k in fc.keyframe_points),
          "Stepped button from the sidebar")
    with override('UI'):
        bpy.ops.mge.set_tangent(kind='CLAMPED', side='BOTH')
    redraw()

    # ---------------------------------------------------------- simplify modal
    print("simplify modal", flush=True)
    frames = list(range(1, 121))
    import math
    dense = [(f, math.sin(f / 8.0) * 2) for f in frames]
    fc.keyframe_points.clear()
    for f, v in dense:
        fc.keyframe_points.insert(f, v)
    select_all(fc)
    view_all()
    yield 0.3
    before = keys_of(fc)
    bpy.context.scene.mge_settings.simplify_tolerance = 0.0
    r = region_of(graph_area(), 'WINDOW')
    cx, cy = r.x + r.width // 3, r.y + r.height // 2
    ev('MOUSEMOVE', 'NOTHING', cx, cy)
    yield 0.1
    with override():
        res = bpy.ops.mge.simplify('INVOKE_DEFAULT')
    check(res == {'RUNNING_MODAL'}, "simplify modal started: %s" % res)
    yield 0.2
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', cx + i * 20, cy)
        yield 0.05
    yield 0.2
    n_preview = len(fc.keyframe_points)
    tol = bpy.context.scene.mge_settings.simplify_tolerance
    check(tol > 0 and n_preview < len(before), "mouse drag raised tolerance to %.2f%%: %d -> %d keys live"
          % (tol, len(before), n_preview))
    redraw()
    shot("04_simplify_preview")
    key('ESC')
    yield 0.3
    check(keys_of(fc) == before and not simplify.is_active(), "Esc restored every key")

    with bpy.context.temp_override(window=win()):
        bpy.ops.ed.undo_push(message="before simplify")
    with override():
        bpy.ops.mge.simplify('INVOKE_DEFAULT')
    yield 0.2
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', cx + i * 20, cy)
        yield 0.05
    key('RET')
    yield 0.3
    n_after = len(fc.keyframe_points)
    check(n_after < len(before) and not simplify.is_active(), "Enter kept the result (%d keys)" % n_after)
    with bpy.context.temp_override(window=win()):
        bpy.ops.ed.undo()
    yield 0.3
    obj = bpy.data.objects[obj_name]  # undo invalidates Python references
    fc = [c for c in _all_fcurves(obj) if c.data_path == "location"][0]
    check(len(fc.keyframe_points) == len(before), "one Ctrl+Z undoes the simplify")

    # background analysis on a big selection
    fc.keyframe_points.clear()
    for f in range(1, 1201):
        fc.keyframe_points.insert(f, math.sin(f / 15.0) * 3 + math.sin(f / 3.1) * 0.05)
    select_all(fc)
    view_all()
    yield 0.3
    with override():
        bpy.ops.mge.simplify('INVOKE_DEFAULT')
    yield 0.05
    planning_seen = simplify.is_active() and simplify._session.planning
    redraw()
    shot("05_simplify_analysing")
    for _ in range(200):
        if simplify.is_active() and not simplify._session.planning:
            break
        yield 0.05
    check(planning_seen, "large selection analysed in the background")
    check(simplify.is_active() and not simplify._session.planning, "analysis finished, preview ready")
    key('ESC')
    yield 0.3
    check(len(fc.keyframe_points) == 1200, "cancel after background analysis changes nothing")

    # ---------------------------------------------------------- retime modal
    print("retime modal", flush=True)
    fc.keyframe_points.clear()
    for f, v in [(1, 0), (11, 3), (21, 1), (31, 4), (41, 0)]:
        fc.keyframe_points.insert(f, v)
    for i, k in enumerate(fc.keyframe_points):
        on = i in (1, 2, 3)
        k.select_control_point = k.select_left_handle = k.select_right_handle = on
    view_all()
    yield 0.3
    seen = []
    real_modal = retime.MGE_OT_retime._modal

    def spy(self, context, event):
        if event.type in {'MOUSEMOVE', 'LEFTMOUSE'}:
            r = region_of(graph_area(), 'WINDOW')
            ses = retime._session
            seen.append("%s/%s mouse=(%d,%d) region=(%d,%d %dx%d) edges_px=(%.1f,%.1f) area_ok=%s" % (
                event.type, event.value, event.mouse_x, event.mouse_y, r.x, r.y, r.width, r.height,
                retime._frame_to_px(r, 1.0, ses.cur[0]) if ses else -1,
                retime._frame_to_px(r, 1.0, ses.cur[1]) if ses else -1,
                context.area is not None and context.area.as_pointer() == graph_area().as_pointer()))
        return real_modal(self, context, event)
    retime.MGE_OT_retime._modal = spy
    with override():
        res = bpy.ops.mge.retime('INVOKE_DEFAULT')
    check(res == {'RUNNING_MODAL'}, "retime lattice opened")
    yield 0.2
    redraw()
    shot("06_retime_lattice")
    r = region_of(graph_area(), 'WINDOW')
    y = r.y + r.height // 2
    x_edge = frame_to_px(31)
    x_target = frame_to_px(51)
    ev('MOUSEMOVE', 'NOTHING', x_edge + 2, y)
    yield 0.1
    check(retime._session.hover == 'R', "hovering the right edge (sent x=%.1f)" % (x_edge + 2))
    for line in seen[-3:]:
        print("    modal saw:", line, flush=True)
    ev('LEFTMOUSE', 'PRESS', x_edge + 2, y)
    yield 0.05
    for i in range(1, 11):
        ev('MOUSEMOVE', 'NOTHING', x_edge + 2 + (x_target - x_edge) * i / 10, y)
        yield 0.03
    ev('LEFTMOUSE', 'RELEASE', x_target + 2, y)
    yield 0.1
    redraw()
    shot("07_retime_dragged")
    frames_now = [k.co[0] for k in fc.keyframe_points]
    check(abs(frames_now[3] - 51) < 1.0 and abs(frames_now[2] - 31) < 1.0 and frames_now[1] == 11,
          "dragging the edge to frame 51 stretched the range x2: %s" % frames_now)
    check(abs(frames_now[4] - 61) < 1.0, "later key rippled along: %s" % frames_now[4])
    key('RET')
    yield 0.2
    check(not retime.is_active(), "Enter closed the lattice")

    span_before = frames_now[3] - frames_now[1]
    with override():
        bpy.ops.mge.retime('INVOKE_DEFAULT')
    yield 0.1
    for t in ('FIVE', 'ZERO'):
        key(t)
        yield 0.05
    key('RET')
    yield 0.3
    frames_now = [k.co[0] for k in fc.keyframe_points]
    check(abs((frames_now[3] - frames_now[1]) - span_before / 2) < 0.5,
          "typing 50 + Enter halved the range: %s" % frames_now)

    # ---------------------------------------------------------- slider tools
    st = bpy.context.scene.mge_settings
    r = region_of(graph_area(), 'WINDOW')
    cx, cy = r.x + r.width // 3, r.y + r.height // 2

    def reset_curve(points, selected):
        fc.keyframe_points.clear()
        for f, v in points:
            fc.keyframe_points.insert(f, v)
        for i, k in enumerate(fc.keyframe_points):
            on = i in selected
            k.select_control_point = k.select_left_handle = k.select_right_handle = on
        view_all()

    print("tween modal", flush=True)
    reset_curve([(1, 0), (11, 2), (21, 5), (31, 10)], {1, 2})
    yield 0.3
    st.tween_bias = 50.0
    ev('MOUSEMOVE', 'NOTHING', cx, cy)
    yield 0.1
    with override():
        res = bpy.ops.mge.tween('INVOKE_DEFAULT')
    check(res == {'RUNNING_MODAL'}, "tween started")
    yield 0.2
    check(all(abs(fc.keyframe_points[i].co[1] - 5.0) < 1e-4 for i in (1, 2)),
          "tween 50%% puts both keys halfway between 0 and 10")
    for i in range(1, 7):
        ev('MOUSEMOVE', 'NOTHING', cx + i * 25, cy)
        yield 0.05
        shot("gif_tween_%02d" % i)
    v_drag = fc.keyframe_points[1].co[1]
    check(v_drag > 5.0 and st.tween_bias > 50, "dragging right moves towards the next key (%.2f, %.0f%%)"
          % (v_drag, st.tween_bias))
    key('RET')
    yield 0.3
    check(not slider._session and abs(fc.keyframe_points[1].co[1] - v_drag) < 1e-4, "Enter kept the tween")

    print("smooth modal", flush=True)
    import math as _m
    reset_curve([(f, _m.sin(f / 6.0) * 2 + (0.6 if f % 2 else -0.6)) for f in range(1, 61)],
                set(range(60)))
    yield 0.3
    before = keys_of(fc)
    st.smooth_sigma = 0.0
    with override():
        bpy.ops.mge.smooth('INVOKE_DEFAULT')
    yield 0.2
    for i in range(1, 7):
        ev('MOUSEMOVE', 'NOTHING', cx + i * 20, cy)
        yield 0.05
        shot("gif_smooth_%02d" % i)
    rough = sum(abs(fc.keyframe_points[i + 1].co[1] - fc.keyframe_points[i].co[1]) for i in range(58))
    rough0 = sum(abs(before[i + 1][1] - before[i][1]) for i in range(58))
    check(st.smooth_sigma > 0 and rough < rough0 * 0.5, "dragging smooths the jitter (%.1f -> %.1f)"
          % (rough0, rough))
    shot("09_smooth_preview")
    key('ESC')
    yield 0.3
    check(keys_of(fc) == before, "Esc restored the jittery keys")

    print("time warp modal", flush=True)
    reset_curve([(f, (f % 10) / 3.0) for f in range(1, 42, 4)], set(range(11)))
    yield 0.3
    st.warp_shape = 'EASE_IN_OUT'
    st.warp_amount = 0.0
    with override():
        bpy.ops.mge.warp('INVOKE_DEFAULT')
    yield 0.2
    for i in range(1, 7):
        ev('MOUSEMOVE', 'NOTHING', cx + i * 30, cy)
        yield 0.05
        shot("gif_warp_%02d" % i)
    xs = [k.co[0] for k in fc.keyframe_points]
    check(xs[0] == 1 and xs[-1] == 41 and xs[1] < 5 and xs[-2] > 37,
          "ease in/out bunches keys at both ends, ends fixed: %s" % [round(x, 1) for x in xs])
    key('RET')
    yield 0.3

    # ---------------------------------------------------------- region lattice: values and move
    print("region lattice", flush=True)
    reset_curve([(1, 0), (11, 1), (21, 3), (31, 2), (41, 0)], {1, 2, 3})
    yield 0.3
    st.retime_ripple = True
    st.region_values = True
    with override():
        bpy.ops.mge.retime('INVOKE_DEFAULT')
    yield 0.2
    r = region_of(graph_area(), 'WINDOW')
    ox, oy, sx, sy = common.view_affine(r)
    top_y = r.y + oy + 3.0 * sy
    mid_x = r.x + ox + 21.0 * sx
    ev('MOUSEMOVE', 'NOTHING', mid_x, top_y)
    yield 0.1
    check(retime._session.hover == 'T', "hovering the top (value) edge: %s" % retime._session.hover)
    shot("10_region_hover_top")
    ev('LEFTMOUSE', 'PRESS', mid_x, top_y)
    yield 0.05
    target_y = r.y + oy + 5.0 * sy
    for i in range(1, 7):
        ev('MOUSEMOVE', 'NOTHING', mid_x, top_y + (target_y - top_y) * i / 6)
        yield 0.04
        shot("gif_region_%02d" % i)
    ev('LEFTMOUSE', 'RELEASE', mid_x, target_y)
    yield 0.1
    vals = [round(k.co[1], 2) for k in fc.keyframe_points]
    check(abs(vals[2] - 5.0) < 0.15 and abs(vals[1] - 1.0) < 0.05 and vals[0] == 0,
          "top edge to value 5 scaled values about the bottom edge: %s" % vals)
    # move the block by dragging inside: +10 frames
    box_mid_y = r.y + oy + 2.5 * sy
    x_in = r.x + ox + 16.0 * sx
    ev('MOUSEMOVE', 'NOTHING', x_in, box_mid_y)
    yield 0.1
    check(retime._session.hover == 'M', "inside the box -> move: %s" % retime._session.hover)
    ev('LEFTMOUSE', 'PRESS', x_in, box_mid_y)
    yield 0.05
    x_to = r.x + ox + 26.0 * sx
    for i in range(1, 5):
        ev('MOUSEMOVE', 'NOTHING', x_in + (x_to - x_in) * i / 4, box_mid_y, ctrl=True, shift=True)
        yield 0.04
    ev('LEFTMOUSE', 'RELEASE', x_to, box_mid_y)
    yield 0.1
    xs = [k.co[0] for k in fc.keyframe_points]
    vals2 = [round(k.co[1], 2) for k in fc.keyframe_points]
    check(xs == [1, 21, 31, 41, 51] and vals2 == vals,
          "Ctrl+Shift drag moved +10 whole frames, values locked, later key rippled: %s" % xs)
    shot("11_region_moved")
    key('RET')
    yield 0.2
    check(not retime.is_active(), "region applied")

    print("cleanup", flush=True)
    reset_curve([(f, _m.sin(f / 9.0) * 3) for f in range(1, 121)], set(range(120)))
    yield 0.2
    with override('UI'):
        res = bpy.ops.mge.cleanup()
    check(res == {'FINISHED'} and len(fc.keyframe_points) < 40,
          "one-click cleanup: 120 -> %d keys" % len(fc.keyframe_points))

    print("translation", flush=True)
    view = bpy.context.preferences.view
    try:
        old = (view.language, view.use_translate_interface)
        view.language = 'ru_RU'
        view.use_translate_interface = True
        got = bpy.app.translations.pgettext_iface("Snapshot")
        check(got == "Снимок", "Russian UI label: %s" % got)
        yield 0.2
        shot("12_sidebar_russian", area_only=False)
        view.language, view.use_translate_interface = old
    except Exception as e:
        check(False, "language switch failed: %s" % e)

    # ---------------------------------------------------------- v1.3 tools
    from maya_graph_editor import blocking, channels, stacked  # noqa: F401
    space = graph_area().spaces.active
    scene = bpy.context.scene

    def deselect_everything():
        for c in _all_fcurves(bpy.data.objects[obj_name]):
            for k in c.keyframe_points:
                k.select_control_point = k.select_left_handle = k.select_right_handle = False

    def blender_draws_key_where_we_think(curve, index):
        """Box-select a 9 px square at the pixel our mapping predicts for a key
        and see whether Blender selects exactly that key."""
        deselect_everything()
        r = region_of(graph_area(), 'WINDOW')
        ox, oy, sx, sy = common.view_affine(r)
        k = curve.keyframe_points[index]
        vscale, voff = common.display_mapping(curve, space, scene)
        nscale, noff = common.nla_mapping(curve)
        px = ox + (k.co[0] * nscale + noff) * common.time_scale(space, scene) * sx
        py = oy + (k.co[1] + voff) * vscale * sy
        with override():
            bpy.ops.graph.select_box(xmin=int(px - 4), xmax=int(px + 5), ymin=int(py - 4),
                                     ymax=int(py + 5), wait_for_input=False, mode='SET')
        hit = [i for i, kk in enumerate(curve.keyframe_points) if kk.select_control_point]
        return hit == [index], "predicted (%.0f, %.0f) px, selected %s" % (px, py, hit)

    print("display mapping vs Blender", flush=True)
    reset_curve([(1, 0), (11, 2), (21, 3.5), (31, 1), (41, 0)], set())
    yield 0.3
    ok, info = blender_draws_key_where_we_think(fc, 2)
    check(ok, "plain curve: key is where the add-on expects it (%s)" % info)
    rot = make_curve([(1, 0.0), (11, 1.0), (21, -0.5), (31, 0.8)], obj_name=obj_name,
                     path="rotation_euler", index=0)
    view_all()
    yield 0.3
    ok, info = blender_draws_key_where_we_think(rot, 1)
    check(ok, "rotation curve shown in degrees (%s)" % info)
    space.use_normalization = True
    view_all()
    yield 0.3
    ok1, info1 = blender_draws_key_where_we_think(rot, 2)
    ok2, info2 = blender_draws_key_where_we_think(fc, 2)
    check(ok1 and ok2, "Normalize on: both curves (%s | %s)" % (info1, info2))
    space.use_normalization = False
    try:
        space.show_seconds = True
        view_all()
        yield 0.3
        ok, info = blender_draws_key_where_we_think(fc, 3)
        check(ok, "seconds display (%s)" % info)
    finally:
        space.show_seconds = False
    view_all()
    yield 0.2
    try:
        cube = bpy.data.objects[obj_name]
        ad = cube.animation_data
        act = ad.action
        track = ad.nla_tracks.new()
        strip = track.strips.new("gui", 40, act)
        strip.scale = 1.5
        ad.action = None
        strip.select = True
        track.select = True
        ad.nla_tracks.active = track
        ad.use_tweak_mode = True
        common.clear_caches()
        yield 0.3
        view_all()
        yield 0.3
        tw = [c for c in _all_fcurves(cube) if c.data_path == "location"][0]
        nscale, noff = common.nla_mapping(tw)
        ok, info = blender_draws_key_where_we_think(tw, 2)
        check(abs(nscale - 1.5) < 1e-3 and ok, "NLA strip (offset 40, scale 1.5) in tweak mode (%s)" % info)
        ad.use_tweak_mode = False
        ad.nla_tracks.remove(track)
        ad.action = act
        if hasattr(ad, "action_slot") and act.slots:
            ad.action_slot = act.slots[0]
        common.clear_caches()
    except Exception as e:
        check(False, "NLA tweak-mode check could not run: %r" % e)
    yield 0.3
    cube = bpy.data.objects[obj_name]
    fc = [c for c in _all_fcurves(cube) if c.data_path == "location"][0]
    rot = [c for c in _all_fcurves(cube) if c.data_path == "rotation_euler"][0]

    print("blocking / channels", flush=True)
    with override('UI'):
        res = bpy.ops.mge.stepped_preview()
    check(res == {'FINISHED'} and all(k.interpolation == 'CONSTANT' for k in fc.keyframe_points)
          and all(k.interpolation == 'CONSTANT' for k in rot.keyframe_points), "stepped preview on")
    redraw()
    shot("13_stepped_preview")
    with override('UI'):
        bpy.ops.mge.stepped_preview()
    check(all(k.interpolation == 'BEZIER' for k in fc.keyframe_points), "stepped preview off restores")
    deselect_everything()
    rot.select, fc.select = True, False
    with override('UI'):
        bpy.ops.mge.channel_set_add(name="rot only")
        fc.select = True
        bpy.ops.mge.channel_set_apply(index=0)
    check(fc.hide and not rot.hide, "channel set shows only its channel")
    with override('UI'):
        bpy.ops.mge.channels_show_all()
    check(not fc.hide and not rot.hide, "show all")
    bpy.context.scene.mge_settings.channel_sets.clear()

    print("auto frame", flush=True)
    st.auto_frame = True
    deselect_everything()
    yield 1.0
    r = region_of(graph_area(), 'WINDOW')
    for k in fc.keyframe_points[:2]:
        k.select_control_point = True
    yield 1.2
    before_view = r.view2d.region_to_view(0, 0)
    deselect_everything()
    for k in fc.keyframe_points[3:]:
        k.select_control_point = True
    yield 1.5
    after_view = r.view2d.region_to_view(0, 0)
    check(abs(after_view[0] - before_view[0]) > 1.0, "view re-framed when the selection changed (%.1f -> %.1f)"
          % (before_view[0], after_view[0]))
    st.auto_frame = False

    print("settle modal / Blender slider", flush=True)
    rot.hide = True
    reset_curve([(1, 0), (11, 6), (60, 6)], {1})
    yield 0.3
    st.settle_amount = 0.0
    r = region_of(graph_area(), 'WINDOW')
    cx, cy = r.x + r.width // 3, r.y + r.height // 2
    ev('MOUSEMOVE', 'NOTHING', cx, cy)
    yield 0.1
    with override():
        res = bpy.ops.mge.settle('INVOKE_DEFAULT')
    check(res == {'RUNNING_MODAL'}, "settle started")
    yield 0.2
    for i in range(1, 7):
        ev('MOUSEMOVE', 'NOTHING', cx + i * 30, cy)
        yield 0.05
    n_keys = len(fc.keyframe_points)
    check(n_keys > 6 and st.settle_amount > 0, "dragging adds the settle keys live (%d keys)" % n_keys)
    shot("14_settle")
    key('ESC')
    yield 0.3
    check(len(fc.keyframe_points) == 3, "Esc removes them again")

    reset_curve([(1, 0), (11, 2), (21, 8), (31, 10)], {1, 2})
    yield 0.3
    before_vals = [k.co[1] for k in fc.keyframe_points]
    ev('MOUSEMOVE', 'NOTHING', cx, cy)
    yield 0.1
    with override('UI'):
        res = bpy.ops.mge.blender_slider(name="blend_to_neighbor")
    check(res == {'FINISHED'}, "Blender's Blend to Neighbor started from the sidebar: %s" % res)
    yield 0.2
    for i in range(1, 6):
        ev('MOUSEMOVE', 'NOTHING', cx + i * 40, cy)
        yield 0.05
    ev('LEFTMOUSE', 'PRESS', cx + 200, cy)
    ev('LEFTMOUSE', 'RELEASE', cx + 200, cy)
    yield 0.3
    after_vals = [k.co[1] for k in fc.keyframe_points]
    check(after_vals != before_vals and after_vals[0] == before_vals[0],
          "its slider changed the selected keys: %s" % [round(v, 2) for v in after_vals])

    print("stacked overview / what's new", flush=True)
    rot.hide = False
    cube = bpy.data.objects[obj_name]
    for i in (0, 1):
        make_curve([(1, i), (15, 2 - i), (30, i * 2), (41, 1)], obj_name=obj_name, path="location", index=i)
    view_all()
    with override('UI'):
        bpy.ops.mge.stacked_toggle()
    for _ in range(2):
        redraw()
        yield 0.1
    shot("15_stacked_overview")
    bpy.context.preferences.addons["maya_graph_editor"].preferences.hud_scale = 1.6
    redraw()
    yield 0.1
    shot("16_stacked_large_text")
    bpy.context.preferences.addons["maya_graph_editor"].preferences.hud_scale = 1.0
    with override('UI'):
        bpy.ops.mge.stacked_toggle()
    with override():
        res = bpy.ops.mge.whats_new('INVOKE_DEFAULT', since="1.2.1")
    yield 0.4
    shot("17_whats_new", area_only=False)
    key('ESC')
    ev('MOUSEMOVE', 'NOTHING', 5, 5)
    yield 0.3
    fc = [c for c in _all_fcurves(cube) if c.data_path == "location" and c.array_index == 2][0]

    # ---------------------------------------------------------- panels / prefs drawn
    print("panels", flush=True)
    for k in fc.keyframe_points:
        k.select_control_point = True
    for _ in range(3):
        redraw()
        yield 0.1
    shot("08_sidebar")
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.userpref_show()
    yield 0.5
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'PREFERENCES':
                bpy.context.preferences.active_section = 'ADDONS'
                a.tag_redraw()
    yield 0.5

    check(not logged, "no errors logged by the add-on: %s" % logged)
    check(not ERRORS, "no Python tracebacks printed (%d)" % len(ERRORS))
    for e in ERRORS[:5]:
        print("----\n" + e)


def _all_fcurves(obj):
    from bpy_helpers import all_fcurves
    return all_fcurves(obj.animation_data.action)


def main():
    gen = sequence()

    def step():
        try:
            delay = next(gen)
            return delay if delay else 0.05
        except StopIteration:
            pass
        except Exception:
            traceback.print_exc()
            FAILS.append("exception in test sequence")
        print("\nGUI FAILURES: %d" % len(FAILS), flush=True)
        for m in FAILS:
            print("  -", m, flush=True)
        sys.stdout.flush()
        os._exit(1 if FAILS else 0)

    bpy.app.timers.register(step, first_interval=1.0)


main()
