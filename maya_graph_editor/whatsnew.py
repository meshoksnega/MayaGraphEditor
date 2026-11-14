""""What's New" popup, shown once after the add-on has been updated."""

import bpy

from . import common

CHANGES = {
    (1, 3, 0): [
        "Blocking: Stepped Preview, Round to Whole Frames, Seamless Loop, Equalize Handles",
        "Stagger and Overlap: offset bones / curves in time, or generate follow-through",
        "Key Sliders: Blender's own slider tools, one click away",
        "Channels: saved channel sets, Isolate, Auto Frame, selection helpers",
        "Noise and Settle generators with live preview",
        "Shape library, and Copy / Paste with Merge, Replace, Insert and Fit",
        "Ghosts from another action, Swap Range, colour-blind-safe palette",
        "Stacked Overview (experimental), larger on-screen text option",
        "Five more languages; settings export / import; faster Simplify",
    ],
    (1, 2, 0): [
        "Region lattice: scale values, move, presets and whole-rig retiming",
        "Tween, Smooth, Time Warp and one-click Mocap Cleanup",
        "Russian and Spanish interface, theme colours",
    ],
}


def current_version():
    from . import bl_info
    return tuple(bl_info["version"])


def _vstr(v):
    return ".".join(str(x) for x in v)


def pending(last_seen, current):
    """Versions with notes that are newer than `last_seen` (a 'x.y.z' string)."""
    try:
        seen = tuple(int(p) for p in last_seen.split("."))
    except ValueError:
        return []
    return sorted((v for v in CHANGES if seen < v <= current), reverse=True)


class MGE_OT_whats_new(bpy.types.Operator):
    bl_idname = "mge.whats_new"
    bl_label = "What's New in Maya Graph Editor Tools"
    bl_description = "Show what changed in recent versions"
    bl_options = {'INTERNAL'}

    since: bpy.props.StringProperty(default="0.0.0")

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=520)

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text=self.bl_label, icon='INFO')
        versions = pending(self.since, current_version()) or sorted(CHANGES, reverse=True)[:1]
        for v in versions:
            box = layout.box()
            box.label(text="Version %s" % _vstr(v))
            col = box.column(align=True)
            for line in CHANGES[v]:
                col.label(text=line, icon='DOT')
        layout.operator("wm.url_open", text="Full release notes", icon='URL').url = \
            "https://github.com/meshoksnega/MayaGraphEditor/releases"


def maybe_show():
    """Timer after startup: show the popup once per update (never on first install)."""
    try:
        prefs = common.get_prefs()
        if prefs is None:
            return None
        cur = _vstr(current_version())
        last = prefs.last_seen_version
        if last == cur:
            return None
        prefs.last_seen_version = cur
        if last and pending(last, current_version()) and prefs.show_whats_new:
            wm = bpy.context.window_manager
            if wm and wm.windows:
                with bpy.context.temp_override(window=wm.windows[0]):
                    bpy.ops.mge.whats_new('INVOKE_DEFAULT', since=last)
    except Exception:
        common.log_exception("what's new")
    return None


classes = (MGE_OT_whats_new,)
