""""What's New": after an update, a short note in the Maya tab and the
preferences links to what changed.  Nothing pops up by itself and no timer
runs; opening the note marks the version as seen."""

import bpy

from . import common

CHANGES = {
    (1, 3, 1): [
        "Leaner: every tool is registered once and the add-on runs no background timers",
        "Switching a tool off hides it instead of unloading it",
        "Auto Frame removed; What's New is now this note instead of a popup",
        "The update check runs only when you click Check for Updates",
    ],
    (1, 3, 0): [
        "Blocking: Stepped Preview, Round to Whole Frames, Seamless Loop, Equalize Handles",
        "Stagger and Overlap: offset bones / curves in time, or generate follow-through",
        "Key Sliders: Blender's own slider tools, one click away",
        "Channels: saved channel sets, Isolate, selection helpers",
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

    since: bpy.props.StringProperty(default="")

    def invoke(self, context, event):
        prefs = common.get_prefs()
        if prefs is not None:
            if not self.since:
                self.since = prefs.last_seen_version or "0.0.0"
            prefs.last_seen_version = _vstr(current_version())  # opened: seen
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


def remember_first_install():
    """On a fresh install there's nothing new to announce: remember the version."""
    try:
        prefs = common.get_prefs()
        if prefs is not None and not prefs.last_seen_version:
            prefs.last_seen_version = _vstr(current_version())
    except Exception:
        pass


def notice_pending():
    prefs = common.get_prefs()
    if prefs is None or not prefs.show_whats_new or not prefs.last_seen_version:
        return False
    return bool(pending(prefs.last_seen_version, current_version()))


def draw_notice(layout):
    if notice_pending():
        layout.operator("mge.whats_new", icon='INFO',
                        text="Updated to %s: what's new" % _vstr(current_version()))


classes = (MGE_OT_whats_new,)
