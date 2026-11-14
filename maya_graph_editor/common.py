"""Shared helpers: curve snapshots, unit/normalisation mapping, drawing, UI utils.

Nothing in here depends on the other tool modules, so it can be imported (and
the data helpers tested) on its own.
"""

import re
import traceback

import numpy as np

import bpy

# Name of the add-on package (differs between legacy add-on / Extension install).
PKG = __package__

TOOL_IDS = ("ghost", "tangents", "simplify", "retime", "curves", "stats")


# --------------------------------------------------------------------------
# Preferences / tool state
# --------------------------------------------------------------------------

def get_prefs():
    try:
        return bpy.context.preferences.addons[PKG].preferences
    except Exception:
        return None


def tool_enabled(name):
    prefs = get_prefs()
    if prefs is None:
        return True
    return bool(getattr(prefs, "enable_" + name, True))


def get_settings(context=None):
    scene = (context or bpy.context).scene
    return scene.mge_settings


# Only one modal tool (simplify / retime) may run at a time.
_modal_owner = None


def modal_claim(name):
    global _modal_owner
    if _modal_owner is not None:
        return False
    _modal_owner = name
    return True


def modal_release(name):
    global _modal_owner
    if _modal_owner == name:
        _modal_owner = None


def modal_owner():
    return _modal_owner


# --------------------------------------------------------------------------
# Context helpers
# --------------------------------------------------------------------------

def graph_poll(context, fcurves_only=True):
    sd = context.space_data
    if sd is None or sd.type != 'GRAPH_EDITOR':
        return False
    return (not fcurves_only) or sd.mode == 'FCURVES'


def _ctx_list(context, name):
    try:
        return list(getattr(context, name) or [])
    except Exception:
        return []


def editable_fcurves(context):
    return _ctx_list(context, "editable_fcurves")


def visible_fcurves(context):
    return _ctx_list(context, "visible_fcurves")


def selected_visible_fcurves(context):
    return _ctx_list(context, "selected_visible_fcurves")


def redraw_graph_editors():
    wm = bpy.context.window_manager
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == 'GRAPH_EDITOR':
                area.tag_redraw()


def window_region(area):
    for region in area.regions:
        if region.type == 'WINDOW':
            return region
    return None


def event_in_region(region, event):
    return (region.x <= event.mouse_x < region.x + region.width and
            region.y <= event.mouse_y < region.y + region.height)


def is_navigation_event(event):
    return event.type in {
        'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE',
        'WHEELOUTMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM', 'MOUSEROTATE',
        'NDOF_MOTION', 'NDOF_BUTTON_FIT', 'INBETWEEN_MOUSEMOVE',
    }


def log_exception(where):
    print("[maya_graph_editor] error in %s:" % where)
    traceback.print_exc()


# --------------------------------------------------------------------------
# F-Curve identity (survives undo, unlike Python references)
# --------------------------------------------------------------------------

def curve_key(fc):
    idb = fc.id_data
    return (idb.name_full if idb is not None else "", fc.data_path, fc.array_index)


def fcurve_map(context):
    return {curve_key(fc): fc for fc in editable_fcurves(context)}


# --------------------------------------------------------------------------
# Keyframe snapshot
# --------------------------------------------------------------------------

_ENUM_ATTRS = ("handle_left_type", "handle_right_type", "interpolation",
               "type", "easing")
_FLOAT_ATTRS = ("back", "amplitude", "period")
_BOOL_ATTRS = ("select_control_point", "select_left_handle",
               "select_right_handle")


def _get_vec2(kps, name, n):
    a = np.empty(n * 2, dtype=np.float32)
    if n:
        kps.foreach_get(name, a)
    return a.reshape(n, 2).astype(np.float64)


class CurveSnapshot:
    """Complete copy of an F-Curve's keyframes; can rebuild the curve from it,
    optionally dropping keys or replacing positions."""

    def capture(self, fc):
        kps = fc.keyframe_points
        n = len(kps)
        self.n = n
        self.co = _get_vec2(kps, "co", n)
        self.hl = _get_vec2(kps, "handle_left", n)
        self.hr = _get_vec2(kps, "handle_right", n)
        self.enums = {a: [getattr(k, a) for k in kps] for a in _ENUM_ATTRS}
        self.floats = {a: [getattr(k, a) for k in kps] for a in _FLOAT_ATTRS}
        self.bools = {a: [getattr(k, a) for k in kps] for a in _BOOL_ATTRS}
        self.extrapolation = fc.extrapolation
        return self

    @classmethod
    def of(cls, fc):
        return cls().capture(fc)

    def copy(self):
        c = CurveSnapshot()
        c.n = self.n
        c.co, c.hl, c.hr = self.co.copy(), self.hl.copy(), self.hr.copy()
        c.enums = {k: list(v) for k, v in self.enums.items()}
        c.floats = {k: list(v) for k, v in self.floats.items()}
        c.bools = {k: list(v) for k, v in self.bools.items()}
        c.extrapolation = self.extrapolation
        return c

    @property
    def selected(self):
        return np.array(self.bools["select_control_point"], dtype=bool)

    def write(self, fc, keep=None, co=None, hl=None, hr=None):
        """Rebuild `fc` from this snapshot (keeping only `keep` indices)."""
        idx = np.arange(self.n) if keep is None else np.asarray(keep, dtype=int)
        co = self.co if co is None else co
        hl = self.hl if hl is None else hl
        hr = self.hr if hr is None else hr
        kps = fc.keyframe_points
        kps.clear()
        m = len(idx)
        if m:
            kps.add(m)
            # Types first, positions last: setting positions through
            # foreach_set does not trigger handle re-calculation, and the
            # final fc.update() does it once for auto/vector handles.
            for j, i in enumerate(idx):
                k = kps[j]
                for a in _ENUM_ATTRS:
                    setattr(k, a, self.enums[a][i])
                for a in _FLOAT_ATTRS:
                    setattr(k, a, self.floats[a][i])
                for a in _BOOL_ATTRS:
                    setattr(k, a, self.bools[a][i])
            kps.foreach_set("co", co[idx].astype(np.float32).ravel())
            kps.foreach_set("handle_left", hl[idx].astype(np.float32).ravel())
            kps.foreach_set("handle_right", hr[idx].astype(np.float32).ravel())
        fc.update()
        try:  # make sure animated objects re-evaluate
            fc.id_data.update_tag()
        except Exception:
            pass


# --------------------------------------------------------------------------
# What the Graph Editor shows vs. raw F-Curve values
# --------------------------------------------------------------------------

_angle_cache = {}
_PATH_RE = re.compile(r'^(.*)\.([A-Za-z_][A-Za-z0-9_]*)(?:\[\d+\])?$')

_ID_COLLECTIONS = ("objects", "materials", "cameras", "lights", "worlds",
                   "scenes", "shape_keys", "meshes", "armatures", "curves",
                   "node_groups", "textures", "grease_pencils", "speakers")


def _animated_ids(action):
    for cname in _ID_COLLECTIONS:
        coll = getattr(bpy.data, cname, None)
        if coll is None:
            continue
        for idb in coll:
            ad = getattr(idb, "animation_data", None)
            if ad is not None and ad.action == action:
                yield idb


def curve_is_angle(fc):
    """True if the Graph Editor displays this channel in degrees."""
    idb = fc.id_data
    key = (idb.name_full if idb is not None else "", fc.data_path)
    hit = _angle_cache.get(key)
    if hit is not None:
        return hit
    result = None
    m = _PATH_RE.match(fc.data_path)
    prefix, prop = (m.group(1), m.group(2)) if m else ("", fc.data_path)
    if idb is not None:
        for owner in _animated_ids(idb):
            try:
                struct = owner.path_resolve(prefix) if prefix else owner
                p = struct.bl_rna.properties.get(prop)
                if p is not None:
                    result = (p.unit == 'ROTATION')
                    break
            except Exception:
                continue
    if result is None:  # could not resolve: fall back on the common names
        result = fc.data_path.endswith("rotation_euler")
    _angle_cache[key] = result
    return result


def clear_caches():
    _angle_cache.clear()


def normalization_params(fc):
    """(factor, offset) used by the Graph Editor's Normalize option."""
    kps = fc.keyframe_points
    n = len(kps)
    if n == 0:
        return 1.0, 0.0
    co = _get_vec2(kps, "co", n)
    hl = _get_vec2(kps, "handle_left", n)
    hr = _get_vec2(kps, "handle_right", n)
    lo = hi = co[0, 1]
    for i in range(n):
        lo = min(lo, co[i, 1])
        hi = max(hi, co[i, 1])
        if i > 0 and kps[i - 1].interpolation == 'BEZIER':
            lo = min(lo, hr[i - 1, 1], hl[i, 1])
            hi = max(hi, hr[i - 1, 1], hl[i, 1])
    rng = hi - lo
    if rng > 1e-7:
        return 2.0 / rng, -lo - rng / 2.0
    return 1.0, -lo


def display_mapping(fc, space, scene):
    """Returns (scale, offset): shown_y = (raw_y + offset) * scale."""
    if getattr(space, "use_normalization", False):
        scale, offset = normalization_params(fc)
        return scale, offset
    if (curve_is_angle(fc) and
            scene.unit_settings.system_rotation == 'DEGREES'):
        return 180.0 / np.pi, 0.0
    return 1.0, 0.0


def time_scale(space, scene):
    """Graph Editor x coordinate = frame * time_scale (seconds display)."""
    if getattr(space, "show_seconds", False):
        return scene.render.fps_base / scene.render.fps
    return 1.0


def sample_curve(fc, step=0.25, max_points=4000, frame_range=None):
    """Densely evaluate a curve -> (n, 2) array.

    Over the keyframe range, or over `frame_range` (start, end) if given, which
    includes extrapolation / cycles outside the keys."""
    kps = fc.keyframe_points
    n = len(kps)
    if n == 0:
        return None
    xs_keys = np.array([k.co[0] for k in kps], dtype=np.float64)
    if frame_range is not None:
        x0, x1 = float(min(frame_range)), float(max(frame_range))
    else:
        x0, x1 = xs_keys.min(), xs_keys.max()
    if x1 - x0 < 1e-6:
        return np.array([[x0, fc.evaluate(x0)]], dtype=np.float64)
    count = int((x1 - x0) / step) + 1
    if count > max_points:
        count = max_points
    xs = np.linspace(x0, x1, count)
    # Stepped segments: add a sample right before each key so the riser is
    # vertical instead of slanted.
    extra = []
    for i in range(1, n):
        if kps[i - 1].interpolation == 'CONSTANT':
            extra.append(xs_keys[i] - 1e-4)
    inside = xs_keys[(xs_keys >= x0) & (xs_keys <= x1)]
    extra = np.array([e for e in extra if x0 <= e <= x1])
    xs = np.unique(np.concatenate([xs, inside, extra]))
    ys = np.array([fc.evaluate(float(x)) for x in xs], dtype=np.float64)
    return np.stack([xs, ys], axis=1)


# --------------------------------------------------------------------------
# View helpers (region pixels <-> curve values)
# --------------------------------------------------------------------------

def view_affine(region):
    """Linear map view->region pixels: returns (ox, oy, sx, sy)."""
    # view_to_region() returns rounded pixels in recent Blender versions, so a
    # scale taken from two nearby points drifts by many pixels across the view.
    # region_to_view() of the region corners gives exact floats instead.
    v2d = region.view2d
    w, h = max(region.width, 1), max(region.height, 1)
    vx0, vy0 = v2d.region_to_view(0, 0)
    vx1, vy1 = v2d.region_to_view(w, h)
    sx = w / (vx1 - vx0) if vx1 != vx0 else 1.0
    sy = h / (vy1 - vy0) if vy1 != vy0 else 1.0
    return -vx0 * sx, -vy0 * sy, sx, sy


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

import blf  # noqa: E402
import gpu  # noqa: E402
from gpu_extras.batch import batch_for_shader  # noqa: E402


def _set_blend(mode):
    try:
        gpu.state.blend_set(mode)
    except Exception:
        pass


def draw_polyline(points, color, width=1.5):
    """points: iterable of (x, y) in region pixels."""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        return
    _set_blend('ALPHA')
    try:
        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINE_STRIP',
                                 {"pos": [(x, y, 0.0) for x, y in pts]})
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        shader.uniform_float("lineWidth", width)
        shader.uniform_float("color", color)
        batch.draw(shader)
    except Exception:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": pts})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
    _set_blend('NONE')


def draw_segments(segments, color, width=1.5):
    """segments: [(x0, y0, x1, y1), ...] in region pixels."""
    if not segments:
        return
    _set_blend('ALPHA')
    try:
        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        pos = []
        for x0, y0, x1, y1 in segments:
            pos.append((float(x0), float(y0), 0.0))
            pos.append((float(x1), float(y1), 0.0))
        batch = batch_for_shader(shader, 'LINES', {"pos": pos})
        shader.bind()
        shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        shader.uniform_float("lineWidth", width)
        shader.uniform_float("color", color)
        batch.draw(shader)
    except Exception:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        pos = []
        for x0, y0, x1, y1 in segments:
            pos += [(float(x0), float(y0)), (float(x1), float(y1))]
        batch = batch_for_shader(shader, 'LINES', {"pos": pos})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
    _set_blend('NONE')


def draw_rect(x0, y0, x1, y1, color):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    verts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    batch = batch_for_shader(shader, 'TRIS', {"pos": verts},
                             indices=[(0, 1, 2), (0, 2, 3)])
    _set_blend('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    _set_blend('NONE')


def draw_text(x, y, text, size=13, color=(1, 1, 1, 1)):
    try:
        blf.size(0, size)
    except TypeError:  # Blender < 4.0 signature
        blf.size(0, size, 72)
    blf.color(0, *color)
    blf.position(0, x, y, 0)
    blf.draw(0, text)


def text_width(text, size=13):
    try:
        blf.size(0, size)
    except TypeError:
        blf.size(0, size, 72)
    return blf.dimensions(0, text)[0]
