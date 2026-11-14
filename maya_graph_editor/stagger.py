"""Tools - Stagger and Overlap (follow-through), both with live preview.

Curves are grouped (per bone / object, or each curve on its own) and the
groups are put in order (channel list order, or bone hierarchy from root to
tip; optionally reversed).

Stagger
    Shifts the selected keys of each group a little later than the group
    before it: group 0 stays, group 1 moves by the offset, group 2 by twice
    the offset...  "Gain" also scales each step's values (about its first
    selected key), e.g. 85% for motion that dies down along a tail.
Overlap
    Generates follow-through: the first group is the leader, and every later
    group gets a delayed, scaled copy of the leader's matching channels
    (same property and axis), starting from its own first key's value.
    It replaces the followers' keys in that time range.
"""

import re

import bpy
import numpy as np

from . import common, slider

_BONE_RE = re.compile(r'pose\.bones\["(.+?)"\]')
_PATH_RE = re.compile(r'^(.*)\.([A-Za-z_][A-Za-z0-9_]*)$')


def split_path(data_path):
    """'pose.bones["a"].rotation_euler' -> ('pose.bones["a"]', 'rotation_euler')."""
    m = _PATH_RE.match(data_path)
    return (m.group(1), m.group(2)) if m else ("", data_path)


def _bone_depth(fc):
    m = _BONE_RE.search(fc.data_path)
    if not m or fc.id_data is None:
        return 0
    for owner in common._animated_ids(fc.id_data):
        pose = getattr(owner, "pose", None)
        bone = pose.bones.get(m.group(1)) if pose else None
        if bone is not None:
            return len(bone.parent_recursive)
    return 0


def build_groups(fcurves, group_mode='BONE', order='CHANNEL', reverse=False):
    """[[fc, ...], ...]: curves grouped and ordered for stagger / overlap."""
    groups, index = [], {}
    for fc in fcurves:
        if group_mode == 'CURVE':
            key = common.curve_key(fc)
        else:
            key = (fc.id_data.name_full if fc.id_data else "", split_path(fc.data_path)[0])
        if key not in index:
            index[key] = len(groups)
            groups.append([])
        groups[index[key]].append(fc)
    if order == 'HIERARCHY':
        depth = [_bone_depth(g[0]) for g in groups]
        groups = [g for _d, _i, g in sorted(zip(depth, range(len(groups)), groups),
                                            key=lambda t: (t[0], t[1]))]
    if reverse:
        groups.reverse()
    return groups


def stagger_curve(snap, level, offset, gain_pct):
    """Selected keys shifted by level*offset frames and scaled by gain**level."""
    sel = snap.selected
    co, hl, hr = snap.co.copy(), snap.hl.copy(), snap.hr.copy()
    if not sel.any() or level == 0:
        return co, hl, hr
    dx = level * offset
    g = (gain_pct / 100.0) ** level
    for a in (co, hl, hr):
        a[sel, 0] += dx
    pivot = snap.co[sel, 1][0]
    co[sel, 1] = pivot + (snap.co[sel, 1] - pivot) * g
    hl[sel, 1] = co[sel, 1] + (snap.hl[sel, 1] - snap.co[sel, 1]) * g
    hr[sel, 1] = co[sel, 1] + (snap.hr[sel, 1] - snap.co[sel, 1]) * g
    return co, hl, hr


def overlap_snapshot(follower, leader, level, delay, gain_pct):
    """Follower curve with a delayed, scaled copy of the leader's keys spliced in."""
    if leader.n == 0:
        return follower
    g = (gain_pct / 100.0) ** level
    dx = level * delay
    rest = follower.co[0, 1] if follower.n else 0.0
    base = leader.co[0, 1]
    co, hl, hr = leader.co.copy(), leader.hl.copy(), leader.hr.copy()
    for a in (co, hl, hr):
        a[:, 0] += dx
    co[:, 1] = rest + (leader.co[:, 1] - base) * g
    hl[:, 1] = co[:, 1] + (leader.hl[:, 1] - leader.co[:, 1]) * g
    hr[:, 1] = co[:, 1] + (leader.hr[:, 1] - leader.co[:, 1]) * g
    gen = common.CurveSnapshot.from_arrays(leader, co, hl, hr, range(leader.n))
    # replace the follower's old motion over the leader's range and the delayed copy
    out = follower.splice(gen, min(leader.co[0, 0], co[0, 0]), max(leader.co[-1, 0], co[-1, 0]))
    out.extrapolation = follower.extrapolation
    return out


def _settings_groups(context, fcurves):
    st = common.get_settings(context)
    return build_groups(fcurves, st.stagger_group, st.stagger_order, st.stagger_reverse)


class StaggerTool(slider.SliderTool):
    id = "stagger"
    label = "STAGGER"
    op_label = "Stagger Selected Keys"
    description = ("Shift the selected keys of each bone / curve a little later than the one "
                   "before it, with a live preview (overlap and follow-through)")
    setting = "stagger_offset"
    vmin, vmax = -12.0, 12.0
    snap_step = 1.0
    marks = (0.0,)

    def prepare(self, context):
        curves = [fc for fc in common.editable_fcurves(context)
                  if any(k.select_control_point for k in fc.keyframe_points)]
        groups = _settings_groups(context, curves)
        if len(groups) < 2:
            return "Select keys on at least two bones / objects (or switch Group to Each Curve)"
        self.gain = common.get_settings(context).stagger_gain
        self.count = len(groups)
        jobs = []
        for level, group in enumerate(groups):
            for fc in group:
                jobs.append(slider.Job(common.curve_key(fc), common.CurveSnapshot.of(fc), level))
        return jobs

    def compute(self, job, value):
        return stagger_curve(job.snap, job.data, value, self.gain)

    def describe(self, value):
        return "%+.1f frames per step   (%d groups)" % (value, getattr(self, "count", 0))


class OverlapTool(slider.SliderTool):
    id = "overlap"
    label = "OVERLAP"
    op_label = "Generate Overlap"
    description = ("Follow-through: copy the first bone's motion onto the rest of the selected "
                   "chain, each one delayed and scaled, with a live preview")
    setting = "overlap_delay"
    vmin, vmax = 0.0, 12.0
    snap_step = 1.0

    def prepare(self, context):
        curves = [fc for fc in common.editable_fcurves(context)
                  if fc.select or any(k.select_control_point for k in fc.keyframe_points)]
        groups = _settings_groups(context, curves)
        if len(groups) < 2:
            return "Select the channels of at least two bones / objects: the first one leads"
        self.gain = common.get_settings(context).overlap_gain
        leader = {}
        for fc in groups[0]:
            snap = common.CurveSnapshot.of(fc)
            if snap.selected.any():
                snap = snap.subset(snap.selected)
            leader[(split_path(fc.data_path)[1], fc.array_index)] = snap
        jobs = []
        for level, group in enumerate(groups[1:], start=1):
            for fc in group:
                src = leader.get((split_path(fc.data_path)[1], fc.array_index))
                if src is not None and src.n:
                    jobs.append(slider.Job(common.curve_key(fc), common.CurveSnapshot.of(fc),
                                           (level, src)))
        self.count = len(groups) - 1
        return jobs or "The followers have no channels matching the leader's (same property and axis)"

    def write(self, job, fc, value):
        level, src = job.data
        overlap_snapshot(job.snap, src, level, value, self.gain).write(fc)

    def describe(self, value):
        return "%.1f frames delay per bone   (%d followers, gain %.0f%%)" % (
            value, getattr(self, "count", 0), getattr(self, "gain", 100.0))


STAGGER = StaggerTool()
OVERLAP = OverlapTool()


class MGE_PT_stagger(bpy.types.Panel):
    bl_label = "Stagger / Overlap"
    bl_idname = "MGE_PT_stagger"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 11
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        layout = self.layout
        st = common.get_settings(context)
        col = layout.column(align=True)
        col.prop(st, "stagger_group", text="")
        row = col.row(align=True)
        row.prop(st, "stagger_order", text="")
        row.prop(st, "stagger_reverse", text="", icon='SORT_DESC')
        box = layout.box()
        box.label(text="Stagger")
        box.prop(st, "stagger_gain", slider=True)
        slider.draw_panel(box, context, STAGGER, 'SORTTIME')
        box = layout.box()
        box.label(text="Overlap")
        box.prop(st, "overlap_gain", slider=True)
        slider.draw_panel(box, context, OVERLAP, 'FORCE_HARMONIC')


classes = (slider.make_operator(STAGGER), slider.make_operator(OVERLAP), MGE_PT_stagger)


def register_tool():
    pass


def unregister_tool():
    slider.unregister_tool_session(STAGGER.id)
    slider.unregister_tool_session(OVERLAP.id)
