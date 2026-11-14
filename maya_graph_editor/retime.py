"""Tool 4 - Region / Retime lattice.

Press "Retime / Region": a box appears around the selected keyframes of all
curves.

  left / right edge   stretch or compress in time (about the opposite edge)
  top / bottom edge   scale values (about the opposite edge)
  corners             both at once
  inside the box      move (Ctrl = whole frames, Shift = one axis only)

Handles are scaled with their keys, so curve shape is kept.  Values are
scaled in Graph Editor display space, so curves in degrees or a normalised
view behave as you see them.  Type a number + Enter to scale time by that
percentage.  Enter / Apply keeps everything, Esc / Cancel restores.

Scope "Whole Rig" retimes every key of the selected objects (or selected
bones in Pose Mode) inside the selection's time range, including channels
that aren't shown; it is time-only.

Panel extras: x0.5 / x2, exact length, fit to preview range or to two
selected markers, anchor at the playhead, and a value scale % about zero,
the first / last key or the centre.
"""

import bpy
import numpy as np

from . import common

GRAB_PX = 10        # how close (pixels) counts as grabbing an edge / corner
_session = None
_last_result = None


# --------------------------------------------------------------------------
# Maths (no UI)
# --------------------------------------------------------------------------

def transform_curve(snap, mask, t0, t1, nt0, nt1, ripple_before=False, ripple_after=False,
                    vbox=None, mapping=(1.0, 0.0)):
    """Map the masked keys of `snap` from box (t0..t1, v0..v1) to (nt0..nt1, nv0..nv1).

    vbox = (v0, v1, nv0, nv1) in display units (None = time only);
    mapping = (scale, offset) with display = (raw + offset) * scale.
    Unmasked keys after/before the range move with the edge when rippling.
    Returns (co, hl, hr)."""
    x, y = snap.co[:, 0], snap.co[:, 1]
    mask = np.asarray(mask, dtype=bool)
    co, hl, hr = snap.co.copy(), snap.hl.copy(), snap.hr.copy()

    st = (nt1 - nt0) / (t1 - t0) if t1 - t0 > 1e-9 else 1.0
    nx = x.copy()
    if t1 - t0 > 1e-9:
        nx[mask] = nt0 + (x[mask] - t0) * st
    else:
        nx[mask] = x[mask] + (nt0 - t0)
    if ripple_after:
        nx[(~mask) & (x > t1)] += nt1 - t1
    if ripple_before:
        nx[(~mask) & (x < t0)] += nt0 - t0
    kx = np.where(mask, st, 1.0)
    co[:, 0] = nx
    hl[:, 0] = nx + (snap.hl[:, 0] - x) * kx
    hr[:, 0] = nx + (snap.hr[:, 0] - x) * kx

    if vbox is not None:
        v0, v1, nv0, nv1 = vbox
        scale, off = mapping
        sv = (nv1 - nv0) / (v1 - v0) if abs(v1 - v0) > 1e-12 else 1.0
        view = (y + off) * scale
        if abs(v1 - v0) > 1e-12:
            nview = nv0 + (view - v0) * sv
        else:
            nview = view + (nv0 - v0)
        ny = np.where(mask, nview / scale - off, y)
        ky = np.where(mask, sv, 1.0)
        co[:, 1] = ny
        hl[:, 1] = ny + (snap.hl[:, 1] - y) * ky
        hr[:, 1] = ny + (snap.hr[:, 1] - y) * ky
    return co, hl, hr


def retime_curve(snap, t0, t1, new_t0, new_t1, ripple):
    """Time-only retime of the selected keys (kept for compatibility)."""
    return transform_curve(snap, snap.selected, t0, t1, new_t0, new_t1,
                           ripple_before=ripple, ripple_after=ripple)


def scale_values(snap, mask, percent, pivot):
    """Scale masked values by `percent` about 'ZERO' / 'FIRST' / 'LAST' / 'CENTER'."""
    mask = np.asarray(mask, dtype=bool)
    y = snap.co[:, 1]
    if not mask.any():
        return snap.co.copy(), snap.hl.copy(), snap.hr.copy()
    ym = y[mask]
    p = {'ZERO': 0.0, 'FIRST': ym[0], 'LAST': ym[-1],
         'CENTER': 0.5 * (ym.min() + ym.max())}[pivot]
    s = percent / 100.0
    co, hl, hr = snap.co.copy(), snap.hl.copy(), snap.hr.copy()
    ny = np.where(mask, p + (y - p) * s, y)
    k = np.where(mask, s, 1.0)
    co[:, 1] = ny
    hl[:, 1] = ny + (snap.hl[:, 1] - y) * k
    hr[:, 1] = ny + (snap.hr[:, 1] - y) * k
    return co, hl, hr


def scaled_range(t0, t1, percent, anchor, playhead=0.0):
    """New (t0, t1) for a range scaled to `percent` about an anchor."""
    s = percent / 100.0
    if anchor == 'RIGHT':
        p = t1
    elif anchor == 'CENTER':
        p = 0.5 * (t0 + t1)
    elif anchor == 'PLAYHEAD':
        p = playhead
    else:
        p = t0
    return p + (t0 - p) * s, p + (t1 - p) * s


def selection_range(snaps):
    xs = [s.co[s.selected, 0] for s in snaps if s.selected.any()]
    if not xs:
        return None
    allx = np.concatenate(xs)
    return float(allx.min()), float(allx.max())


# --------------------------------------------------------------------------
# Whole-rig scope
# --------------------------------------------------------------------------

def rig_fcurves(context):
    """F-Curves of the selected objects (selected bones only in Pose Mode)."""
    objs = list(getattr(context, "selected_objects", None) or [])
    active = getattr(context, "active_object", None)
    if active is not None and active not in objs:
        objs.append(active)
    bone_prefixes = None
    pose_bones = getattr(context, "selected_pose_bones", None)
    if active is not None and active.mode == 'POSE' and pose_bones:
        bone_prefixes = tuple('pose.bones["%s"]' % b.name for b in pose_bones)
    out, seen = [], set()
    for obj in objs:
        ad = obj.animation_data
        if ad is None or ad.action is None:
            continue
        slot = getattr(ad, "action_slot", None)
        for fc in common.action_fcurves(ad.action, slot):
            if fc.lock:
                continue
            if bone_prefixes is not None and obj == active and \
                    not fc.data_path.startswith(bone_prefixes):
                continue
            key = common.curve_key(fc)
            if key not in seen:
                seen.add(key)
                out.append(fc)
    return out


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------

class CurveState:
    __slots__ = ("key", "orig", "base", "mask", "mapping")


class Session:
    def __init__(self, area):
        self.area_ptr = area.as_pointer()
        self.curves = []
        self.scope = 'SELECTED'
        self.values = True               # value edges available
        self.t0 = self.t1 = 0.0          # committed box
        self.v0 = self.v1 = 0.0
        self.cur = (0.0, 0.0, 0.0, 0.0)  # live box (t0, t1, v0, v1)
        self.drag = None                 # None | L R T B TL TR BL BR M
        self.grab = (0.0, 0.0)
        self.hover = None
        self.handle = None
        self.cursor_window = None
        self.typed = ""


def _value_box(curves):
    vs = []
    for c in curves:
        scale, off = c.mapping
        y = c.base.co[c.mask, 1]
        if len(y):
            vs.append((y + off) * scale)
    if not vs:
        return 0.0, 0.0
    allv = np.concatenate(vs)
    return float(allv.min()), float(allv.max())


def _begin(context, scope=None):
    st = common.get_settings(context)
    ses = Session(context.area)
    ses.scope = scope or st.retime_scope
    space, scene = getattr(context, "space_data", None), context.scene
    visible = []
    for fc in common.editable_fcurves(context):
        snap = common.CurveSnapshot.of(fc)
        visible.append((fc, snap))
    rng = selection_range([s for _fc, s in visible])
    if rng is None or rng[1] - rng[0] < 1e-4:
        return None
    t0, t1 = rng
    if ses.scope == 'RIG':
        ses.values = False
        for fc in rig_fcurves(context):
            snap = common.CurveSnapshot.of(fc)
            mask = (snap.co[:, 0] >= t0 - 1e-6) & (snap.co[:, 0] <= t1 + 1e-6)
            if mask.any():
                ses.curves.append(_state(fc, snap, mask, (1.0, 0.0)))
    else:
        ses.values = bool(st.region_values)
        for fc, snap in visible:
            if snap.selected.any():
                mapping = common.display_mapping(fc, space, scene) if space else (1.0, 0.0)
                ses.curves.append(_state(fc, snap, snap.selected, mapping))
    if not ses.curves:
        return None
    ses.t0, ses.t1 = t0, t1
    ses.v0, ses.v1 = _value_box(ses.curves)
    ses.cur = (ses.t0, ses.t1, ses.v0, ses.v1)
    return ses


def _state(fc, snap, mask, mapping):
    cs = CurveState()
    cs.key, cs.orig, cs.base = common.curve_key(fc), snap, snap.copy()
    cs.mask, cs.mapping = np.asarray(mask, dtype=bool), mapping
    return cs


def _lookup(context, ses):
    fmap = common.fcurve_map(context)
    if ses.scope == 'RIG':
        for fc in rig_fcurves(context):
            fmap.setdefault(common.curve_key(fc), fc)
    return fmap


def _apply_box(context, nt0, nt1, nv0=None, nv1=None, ses=None):
    ses = ses or _session
    st = common.get_settings(context)
    ripple = st.retime_ripple
    drag = ses.drag or ""
    left_edge = 'L' in drag and drag != 'M'
    vbox = None
    if ses.values and nv0 is not None:
        vbox = (ses.v0, ses.v1, nv0, nv1)
    fmap = _lookup(context, ses)
    for c in ses.curves:
        fc = fmap.get(c.key)
        if fc is None:
            continue
        co, hl, hr = transform_curve(
            c.base, c.mask, ses.t0, ses.t1, nt0, nt1,
            ripple_before=ripple and left_edge, ripple_after=ripple,
            vbox=vbox, mapping=c.mapping)
        c.base.write(fc, co=co, hl=hl, hr=hr)
    ses.cur = (nt0, nt1, ses.v0 if nv0 is None else nv0, ses.v1 if nv1 is None else nv1)
    live = _normalized_box(context, ses, fmap)
    if live is not None:  # Normalize re-scales the display as values change
        ses.cur = (nt0, nt1, live[0], live[1])
    common.redraw_graph_editors()


def _normalized_box(context, ses, fmap, update_mapping=False):
    """With Normalize on, the value box as Blender currently displays it."""
    space = getattr(context, "space_data", None)
    if not ses.values or space is None or not getattr(space, "use_normalization", False):
        return None
    vs = []
    for c in ses.curves:
        fc = fmap.get(c.key)
        if fc is None:
            continue
        scale, off = common.display_mapping(fc, space, context.scene)
        if update_mapping:
            c.mapping = (scale, off)
        ys = [k.co[1] for k, m in zip(fc.keyframe_points, c.mask) if m]
        vs.extend((y + off) * scale for y in ys)
    return (min(vs), max(vs)) if vs else None


def _commit(context, ses=None):
    """Make the current state the new base for the next drag."""
    ses = ses or _session
    fmap = _lookup(context, ses)
    for c in ses.curves:
        fc = fmap.get(c.key)
        if fc is None:
            continue
        c.base = common.CurveSnapshot.of(fc)
        if ses.scope != 'RIG':  # rig scope keeps its time-range mask
            c.mask = c.base.selected
    live = _normalized_box(context, ses, fmap, update_mapping=True)
    if live is not None:
        ses.cur = (ses.cur[0], ses.cur[1], live[0], live[1])
    ses.t0, ses.t1, ses.v0, ses.v1 = ses.cur
    ses.drag = None


def _restore_base(context):
    ses = _session
    fmap = _lookup(context, ses)
    for c in ses.curves:
        fc = fmap.get(c.key)
        if fc is not None:
            c.base.write(fc)
    ses.cur = (ses.t0, ses.t1, ses.v0, ses.v1)
    ses.drag = None


def is_active():
    return _session is not None


def retime_to(context, new_t0, new_t1):
    """Retime to an exact range, inside a session or directly on the selection."""
    ses = _session or _begin(context)
    if ses is None:
        return None
    _apply_box(context, new_t0, new_t1, ses=ses)
    _commit(context, ses)
    return new_t0, new_t1


def scale_selection(context, percent, anchor):
    """Retime by a percentage about an anchor. Returns the new range or None."""
    ses = _session or _begin(context)
    if ses is None:
        return None
    new = scaled_range(ses.t0, ses.t1, percent, anchor, float(context.scene.frame_current))
    _apply_box(context, new[0], new[1], ses=ses)
    _commit(context, ses)
    return new


def scale_selection_values(context, percent, pivot):
    """Scale the values of the session's / selection's keys about a pivot."""
    ses = _session or _begin(context, scope='SELECTED')
    if ses is None or ses.scope == 'RIG':
        return False
    fmap = _lookup(context, ses)
    for c in ses.curves:
        fc = fmap.get(c.key)
        if fc is not None:
            co, hl, hr = scale_values(c.base, c.mask, percent, pivot)
            c.base.write(fc, co=co, hl=hl, hr=hr)
    ses.cur = (ses.t0, ses.t1, ses.v0, ses.v1)
    _commit(context, ses)
    ses.v0, ses.v1 = _value_box(ses.curves)
    ses.cur = (ses.t0, ses.t1, ses.v0, ses.v1)
    common.redraw_graph_editors()
    return True


def abort_session():
    """Drop a session without touching any data (e.g. a new file is loading)."""
    global _session
    ses = _session
    if ses is None:
        return
    if ses.handle is not None:
        try:
            bpy.types.SpaceGraphEditor.draw_handler_remove(ses.handle, 'WINDOW')
        except Exception:
            pass
    common.modal_release("retime")
    _session = None


def finish(context, apply):
    global _session, _last_result
    ses = _session
    if ses is None:
        return
    if apply:
        if ses.drag is not None:
            _commit(context)
        from . import blocking
        fmap = _lookup(context, ses)
        blocking.auto_round(context, [fmap[c.key] for c in ses.curves if c.key in fmap])
    else:
        fmap = _lookup(context, ses)
        for c in ses.curves:
            fc = fmap.get(c.key)
            if fc is not None:
                c.orig.write(fc)
    if ses.handle is not None:
        bpy.types.SpaceGraphEditor.draw_handler_remove(ses.handle, 'WINDOW')
    try:
        context.workspace.status_text_set(None)
    except Exception:
        pass
    try:
        (ses.cursor_window or context.window).cursor_set('DEFAULT')
    except Exception:
        pass
    common.modal_release("retime")
    _session = None
    _last_result = 'APPLY' if apply else 'CANCEL'
    common.redraw_graph_editors()


# --------------------------------------------------------------------------
# Geometry in pixels
# --------------------------------------------------------------------------

def _frame_to_px(region, tscale, frame):
    ox, _oy, sx, _sy = common.view_affine(region)
    return ox + frame * tscale * sx


def _box_px(region, tscale, box):
    ox, oy, sx, sy = common.view_affine(region)
    t0, t1, v0, v1 = box
    xl, xr = ox + t0 * tscale * sx, ox + t1 * tscale * sx
    yb, yt = oy + v0 * sy, oy + v1 * sy
    if yt - yb < 16:  # flat selection: give the box some height to grab
        mid = 0.5 * (yb + yt)
        yb, yt = mid - 8, mid + 8
    return xl, xr, yb, yt


def hit_test(ses, mx, my, xl, xr, yb, yt):
    """Which part of the lattice is under (mx, my) in region pixels."""
    g = GRAB_PX
    if ses.values:
        for name, cx, cy in (('TL', xl, yt), ('TR', xr, yt), ('BL', xl, yb), ('BR', xr, yb)):
            if abs(mx - cx) <= g and abs(my - cy) <= g:
                return name
        if xl - g <= mx <= xr + g:
            if abs(my - yt) <= g:
                return 'T'
            if abs(my - yb) <= g:
                return 'B'
    dl, dr = abs(mx - xl), abs(mx - xr)
    if min(dl, dr) <= g:
        return 'L' if dl < dr else 'R'
    if xl < mx < xr and (not ses.values or yb < my < yt):
        return 'M'
    return None


_CURSORS = {'L': 'MOVE_X', 'R': 'MOVE_X', 'T': 'MOVE_Y', 'B': 'MOVE_Y', 'M': 'HAND',
            'TL': 'SCROLL_XY', 'TR': 'SCROLL_XY', 'BL': 'SCROLL_XY', 'BR': 'SCROLL_XY'}


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def _draw_lattice():
    ses = _session
    ctx = bpy.context
    if ses is None or ctx.area is None or ctx.area.as_pointer() != ses.area_ptr:
        return
    region, space, scene = ctx.region, ctx.space_data, ctx.scene
    if region is None or region.type != 'WINDOW':
        return
    try:
        col = common.ui_colors()
        accent, active_col = col["accent"], col["active"]
        tscale = common.time_scale(space, scene)
        h = region.height
        xl, xr, yb, yt = _box_px(region, tscale, ses.cur)
        common.draw_rect(xl, 0, xr, h, common.with_alpha(accent, 0.08))

        def colour(part):
            on = ses.drag == part or (ses.drag is None and ses.hover == part)
            return active_col if on else accent

        for part, x in (('L', xl), ('R', xr)):
            c = colour(part)
            common.draw_polyline([(x, 0), (x, h)], c, 2.0 if c is active_col else 1.5)
            common.draw_rect(x - 6, h / 2 - 22, x + 6, h / 2 + 22, c)
            common.draw_rect(x - 1, h / 2 - 12, x + 1, h / 2 + 12, col["bg"])
        if ses.values:
            inside = colour('M')
            common.draw_rect(xl, yb, xr, yt, common.with_alpha(inside, 0.10 if inside is accent else 0.18))
            for part, y in (('T', yt), ('B', yb)):
                c = colour(part)
                common.draw_polyline([(xl, y), (xr, y)], c, 2.0 if c is active_col else 1.5)
                mx = 0.5 * (xl + xr)
                common.draw_rect(mx - 22, y - 5, mx + 22, y + 5, c)
            for part, x, y in (('TL', xl, yt), ('TR', xr, yt), ('BL', xl, yb), ('BR', xr, yb)):
                c = colour(part)
                common.draw_rect(x - 6, y - 6, x + 6, y + 6, c)
                common.draw_rect(x - 3, y - 3, x + 3, y + 3, col["bg"])

        t0, t1, v0, v1 = ses.cur
        w0, w1 = ses.t1 - ses.t0, t1 - t0
        pct = 100.0 * w1 / w0 if w0 else 100.0
        title = "RETIME" if ses.scope != 'RIG' else "RETIME (whole rig)"
        label = "%s   %.1f → %.1f   (length %.1f → %.1f, %.0f%%)" % (
            title, t0, t1, w0, w1, pct)
        if ses.values and abs(ses.v1 - ses.v0) > 1e-9:
            label += "   values %.0f%%" % (100.0 * (v1 - v0) / (ses.v1 - ses.v0))
        tx = min(max(xl, 12) + 8, max(region.width - 520, 12))
        common.draw_rect(tx - 6, h - 32, tx + common.text_width(label, 14) + 8, h - 10, col["bg"])
        common.draw_text(tx, h - 26, label, 14, col["text"])
        if ses.typed:
            common.draw_text(tx, h - 48, "Scale time: %s%%  (Enter = apply)" % ses.typed,
                             14, active_col)
        hint = ("drag edges: time / values · corners: both · inside: move (Shift = one axis) "
                "· Ctrl = whole frames · type a % · Enter = apply · Esc = cancel")
        common.draw_rect(6, 4, 14 + common.text_width(hint, 11), 24, col["bg"])
        common.draw_text(12, 10, hint, 11, col["dim"])
    except Exception:
        common.log_exception("retime draw")


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class MGE_OT_retime(bpy.types.Operator):
    bl_idname = "mge.retime"
    bl_label = "Retime / Region"
    bl_description = ("Show a lattice around the selected keyframes (across all curves): "
                      "drag its edges to retime or scale values, its corners for both, "
                      "inside to move")
    bl_options = {'UNDO', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None

    def invoke(self, context, event):
        global _session
        ses = _begin(context)
        if ses is None:
            self.report({'WARNING'}, "Select keyframes spanning at least two different frames")
            return {'CANCELLED'}
        if not common.modal_claim("retime"):
            return {'CANCELLED'}
        ses.handle = bpy.types.SpaceGraphEditor.draw_handler_add(
            _draw_lattice, (), 'WINDOW', 'POST_PIXEL')
        ses.cursor_window = context.window
        _session = ses
        context.workspace.status_text_set(
            "Region: drag edges / corners / inside   Ctrl: whole frames   Shift: one axis   "
            "type %: scale time   Enter: apply   Esc/RMB: cancel")
        context.window_manager.modal_handler_add(self)
        common.redraw_graph_editors()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if _session is None:  # finished from the sidebar buttons
            return {'FINISHED'} if _last_result == 'APPLY' else {'CANCELLED'}
        try:
            return self._modal(context, event)
        except Exception:
            common.log_exception("retime modal")
            finish(context, apply=False)
            return {'CANCELLED'}

    def _mouse(self, context, region, event):
        scene, space = context.scene, context.space_data
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        vx, vy = region.view2d.region_to_view(mx, my)
        return vx / common.time_scale(space, scene), vy, mx, my

    def _modal(self, context, event):
        ses = _session
        if not common.tool_enabled("retime") or context.area is None:
            finish(context, apply=False)
            return {'CANCELLED'}
        region = common.window_region(context.area)
        if region is None:
            return {'PASS_THROUGH'}
        inside = common.event_in_region(region, event)
        dragging = ses.drag is not None

        if event.value == 'PRESS' and not dragging:
            char = _TYPED_KEYS.get(event.type)
            if char is not None:
                if char != "." or "." not in ses.typed:
                    ses.typed += char
                common.redraw_graph_editors()
                return {'RUNNING_MODAL'}
            if event.type == 'BACK_SPACE' and ses.typed:
                ses.typed = ses.typed[:-1]
                common.redraw_graph_editors()
                return {'RUNNING_MODAL'}

        if event.value == 'PRESS':
            if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and (inside or dragging)):
                if dragging:
                    _restore_base(context)
                    return {'RUNNING_MODAL'}
                if ses.typed:
                    ses.typed = ""
                    common.redraw_graph_editors()
                    return {'RUNNING_MODAL'}
                finish(context, apply=False)
                return {'CANCELLED'}
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
                if ses.typed:
                    try:
                        pct = float(ses.typed)
                    except ValueError:
                        pct = 0.0
                    ses.typed = ""
                    if pct > 0.0:
                        scale_selection(context, pct, common.get_settings(context).retime_anchor)
                finish(context, apply=True)
                return {'FINISHED'}

        if not (inside or dragging):
            ses.hover = None
            return {'PASS_THROUGH'}

        frame, vy, mx, my = self._mouse(context, region, event)
        tscale = common.time_scale(context.space_data, context.scene)

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and not dragging:
            if ses.hover:
                ses.drag = ses.hover
                ses.grab = (frame, vy, mx, my)
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and dragging:
            _commit(context)
            return {'RUNNING_MODAL'}

        if event.type == 'MOUSEMOVE':
            if dragging:
                self._drag(context, ses, frame, vy, mx, my, event)
            else:
                xl, xr, yb, yt = _box_px(region, tscale, ses.cur)
                hover = hit_test(ses, mx, my, xl, xr, yb, yt)
                if hover != ses.hover:
                    ses.hover = hover
                    common.redraw_graph_editors()
                try:
                    context.window.cursor_set(_CURSORS.get(hover, 'DEFAULT'))
                except Exception:
                    pass
            return {'RUNNING_MODAL'}

        if common.is_navigation_event(event):
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def _drag(self, context, ses, frame, vy, mx, my, event):
        st = common.get_settings(context)
        gf, gv, gmx, gmy = ses.grab
        t0, t1, v0, v1 = ses.t0, ses.t1, ses.v0, ses.v1
        snap = event.ctrl or st.retime_snap
        part = ses.drag
        nt0, nt1, nv0, nv1 = t0, t1, v0, v1
        if part == 'M':
            dt, dv = frame - gf, vy - gv
            if event.shift:  # lock to the axis that moved most on screen
                if abs(mx - gmx) >= abs(my - gmy):
                    dv = 0.0
                else:
                    dt = 0.0
            if snap:
                dt = round(dt)
            nt0, nt1 = t0 + dt, t1 + dt
            if ses.values:
                nv0, nv1 = v0 + dv, v1 + dv
        else:
            min_len = max((t1 - t0) * 0.02, 0.01)
            if 'R' in part:
                target = t1 + frame - gf
                nt1 = max(round(target) if snap else target, t0 + min_len)
            if 'L' in part:
                target = t0 + frame - gf
                nt0 = min(round(target) if snap else target, t1 - min_len)
            if ses.values and (abs(v1 - v0) > 1e-12):
                min_h = abs(v1 - v0) * 0.02
                if 'T' in part:
                    nv1 = max(v1 + vy - gv, v0 + min_h)
                if 'B' in part:
                    nv0 = min(v0 + vy - gv, v1 - min_h)
        if ses.values:
            _apply_box(context, nt0, nt1, nv0, nv1)
        else:
            _apply_box(context, nt0, nt1)


_TYPED_KEYS = {**{n: str(i) for i, n in enumerate(
    ("ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"))},
    **{"NUMPAD_%d" % i: str(i) for i in range(10)}, "PERIOD": ".", "NUMPAD_PERIOD": "."}


def _poll_tool(context):
    return common.graph_poll(context) and common.modal_owner() in (None, "retime")


class MGE_OT_retime_scale(bpy.types.Operator):
    bl_idname = "mge.retime_scale"
    bl_label = "Scale Time"
    bl_description = ("Stretch or compress the selected keys (or the open lattice) by a "
                      "percentage, about the chosen anchor")
    bl_options = {'REGISTER', 'UNDO'}

    percent: bpy.props.FloatProperty(name="Scale", default=-1.0, subtype='PERCENTAGE')

    @classmethod
    def poll(cls, context):
        return _poll_tool(context)

    def execute(self, context):
        st = common.get_settings(context)
        pct = self.percent if self.percent > 0 else st.retime_percent
        if scale_selection(context, pct, st.retime_anchor) is None:
            self.report({'WARNING'}, "Select keyframes spanning at least two different frames")
            return {'CANCELLED'}
        return {'FINISHED'}


class MGE_OT_retime_length(bpy.types.Operator):
    bl_idname = "mge.retime_length"
    bl_label = "Set Length"
    bl_description = "Retime the selection to exactly this many frames, about the chosen anchor"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _poll_tool(context)

    def execute(self, context):
        st = common.get_settings(context)
        ses = _session or _begin(context)
        if ses is None or ses.t1 - ses.t0 < 1e-6:
            self.report({'WARNING'}, "Select keyframes spanning at least two different frames")
            return {'CANCELLED'}
        pct = 100.0 * st.retime_length / (ses.t1 - ses.t0)
        new = scaled_range(ses.t0, ses.t1, pct, st.retime_anchor, float(context.scene.frame_current))
        _apply_box(context, new[0], new[1], ses=ses)
        _commit(context, ses)
        return {'FINISHED'}


class MGE_OT_retime_fit(bpy.types.Operator):
    bl_idname = "mge.retime_fit"
    bl_label = "Fit"
    bl_description = "Retime the selection to fill a frame range exactly"
    bl_options = {'REGISTER', 'UNDO'}

    target: bpy.props.EnumProperty(items=(
        ('PREVIEW', "Preview Range", "The preview range (or the scene range if none)"),
        ('MARKERS', "Selected Markers", "Between the first and last selected marker"),
    ))

    @classmethod
    def poll(cls, context):
        return _poll_tool(context)

    def execute(self, context):
        scene = context.scene
        if self.target == 'MARKERS':
            frames = sorted(m.frame for m in scene.timeline_markers if m.select)
            if len(frames) < 2:
                self.report({'WARNING'}, "Select two markers first")
                return {'CANCELLED'}
            a, b = frames[0], frames[-1]
        elif scene.use_preview_range:
            a, b = scene.frame_preview_start, scene.frame_preview_end
        else:
            a, b = scene.frame_start, scene.frame_end
        if retime_to(context, float(a), float(b)) is None:
            self.report({'WARNING'}, "Select keyframes spanning at least two different frames")
            return {'CANCELLED'}
        return {'FINISHED'}


class MGE_OT_region_value_scale(bpy.types.Operator):
    bl_idname = "mge.region_value_scale"
    bl_label = "Scale Values"
    bl_description = "Scale the values of the selected keys by a percentage about a pivot"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _poll_tool(context)

    def execute(self, context):
        st = common.get_settings(context)
        if not scale_selection_values(context, st.region_value_percent, st.region_pivot):
            self.report({'WARNING'}, "Select keyframes (value scaling is not available for "
                        "the whole-rig scope)")
            return {'CANCELLED'}
        return {'FINISHED'}


class MGE_OT_retime_confirm(bpy.types.Operator):
    bl_idname = "mge.retime_confirm"
    bl_label = "Apply"
    bl_description = "Keep the result"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return is_active()

    def execute(self, context):
        finish(context, apply=True)
        return {'FINISHED'}


class MGE_OT_retime_cancel(bpy.types.Operator):
    bl_idname = "mge.retime_cancel"
    bl_label = "Cancel"
    bl_description = "Put every key back where it was"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return is_active()

    def execute(self, context):
        finish(context, apply=False)
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------

class MGE_PT_retime(bpy.types.Panel):
    bl_label = "Retime / Region"
    bl_idname = "MGE_PT_retime"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 4

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        layout.row().prop(st, "retime_scope", expand=True)
        col = layout.column(align=True)
        col.prop(st, "retime_ripple")
        col.prop(st, "retime_snap")
        sub = col.row()
        sub.active = st.retime_scope != 'RIG'
        sub.prop(st, "region_values")

        if is_active():
            ses = _session
            w0, w1 = ses.t1 - ses.t0, ses.cur[1] - ses.cur[0]
            layout.label(text="%.1f → %.1f frames (%.0f%%)" % (
                w0, w1, 100.0 * w1 / w0 if w0 else 100.0))
            row = layout.row(align=True)
            row.scale_y = 1.3
            row.operator("mge.retime_confirm", icon='CHECKMARK')
            row.operator("mge.retime_cancel", icon='X')
        else:
            row = layout.row()
            row.scale_y = 1.3
            row.operator("mge.retime", icon='ARROW_LEFTRIGHT')

        box = layout.box()
        box.label(text="Time", icon='TIME')
        box.prop(st, "retime_anchor", text="Anchor")
        row = box.row(align=True)
        row.prop(st, "retime_percent", text="")
        row.operator("mge.retime_scale", text="", icon='CHECKMARK')
        row = box.row(align=True)
        row.operator("mge.retime_scale", text="×0.5").percent = 50.0
        row.operator("mge.retime_scale", text="×2").percent = 200.0
        row = box.row(align=True)
        row.prop(st, "retime_length", text="Length")
        row.operator("mge.retime_length", text="", icon='CHECKMARK')
        row = box.row(align=True)
        row.operator("mge.retime_fit", text="Fit Preview Range").target = 'PREVIEW'
        row.operator("mge.retime_fit", text="Fit Markers").target = 'MARKERS'

        box = layout.box()
        box.active = st.retime_scope != 'RIG'
        box.label(text="Values", icon='FCURVE')
        box.prop(st, "region_pivot", text="Pivot")
        row = box.row(align=True)
        row.prop(st, "region_value_percent", text="")
        row.operator("mge.region_value_scale", text="", icon='CHECKMARK')


classes = (MGE_OT_retime, MGE_OT_retime_scale, MGE_OT_retime_length, MGE_OT_retime_fit,
           MGE_OT_region_value_scale, MGE_OT_retime_confirm, MGE_OT_retime_cancel,
           MGE_PT_retime)


def register_tool():
    pass


def unregister_tool():
    if _session is not None:
        try:
            finish(bpy.context, apply=False)
        except Exception:
            common.log_exception("retime unregister")
