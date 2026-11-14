"""Export / import the add-on's settings (tool options, enabled tools,
shortcuts, channel sets) as a JSON file, to move them between machines."""

import json

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import common, keymaps

FORMAT = 1
_SKIP_SETTINGS = {"rna_type", "name", "stats_frame", "stats_value", "new_key_tangent",
                  "ghost_source", "channel_sets", "stacked_show", "shape_active"}
_SKIP_PREFS = {"rna_type", "bl_idname", "update_last_check", "last_seen_version"}


def _dump(group, skip):
    out = {}
    if not hasattr(group, "bl_rna"):
        return out
    for p in group.bl_rna.properties:
        if p.identifier in skip or p.type in {'POINTER', 'COLLECTION'}:
            continue
        v = getattr(group, p.identifier)
        out[p.identifier] = list(v) if hasattr(v, "__len__") and not isinstance(v, str) else v
    return out


def _load(group, data, skip):
    applied = 0
    if not hasattr(group, "bl_rna"):
        return applied
    for name, value in data.items():
        if name in skip or name not in group.bl_rna.properties:
            continue
        try:
            setattr(group, name, value)
            applied += 1
        except Exception:
            pass
    return applied


def _user_kmi(idname, props):
    kc = bpy.context.window_manager.keyconfigs.user
    km = kc.keymaps.get("Graph Editor") if kc else None
    for kmi in (km.keymap_items if km else ()):
        if keymaps._matches(kmi, idname, props):
            return kmi
    return None


def export_dict(context):
    st = common.get_settings(context)
    prefs = common.get_prefs()
    shortcuts = []
    for tool, entries in keymaps.DEFAULTS.items():
        for idname, _key, _c, _s, _a, props in entries:
            kmi = _user_kmi(idname, props)
            if kmi is not None:
                shortcuts.append({"idname": idname, "props": props, "type": kmi.type,
                                  "ctrl": bool(kmi.ctrl), "shift": bool(kmi.shift),
                                  "alt": bool(kmi.alt), "active": bool(kmi.active)})
    return {
        "maya_graph_editor_settings": FORMAT,
        "settings": _dump(st, _SKIP_SETTINGS),
        "preferences": _dump(prefs, _SKIP_PREFS) if prefs is not None else {},
        "channel_sets": [{"name": c.name, "data": c.data} for c in st.channel_sets],
        "shortcuts": shortcuts,
    }


def import_dict(context, data):
    """Returns the number of values applied; raises ValueError for a foreign file."""
    if not isinstance(data, dict) or "maya_graph_editor_settings" not in data:
        raise ValueError("Not a Maya Graph Editor Tools settings file")
    st = common.get_settings(context)
    n = _load(st, data.get("settings", {}), _SKIP_SETTINGS)
    prefs = common.get_prefs()
    if prefs is not None:
        n += _load(prefs, data.get("preferences", {}), _SKIP_PREFS)
    have = {c.name for c in st.channel_sets}
    for item in data.get("channel_sets", []):
        if item.get("name") and item["name"] not in have:
            c = st.channel_sets.add()
            c.name, c.data = item["name"], item.get("data", "[]")
            n += 1
    for sc in data.get("shortcuts", []):
        kmi = _user_kmi(sc.get("idname", ""), sc.get("props", {}))
        if kmi is not None:
            try:
                kmi.type = sc["type"]
                kmi.ctrl, kmi.shift, kmi.alt = sc["ctrl"], sc["shift"], sc["alt"]
                kmi.active = sc.get("active", True)
                n += 1
            except Exception:
                pass
    return n


class MGE_OT_settings_export(bpy.types.Operator, ExportHelper):
    bl_idname = "mge.settings_export"
    bl_label = "Export Settings"
    bl_description = "Save the add-on's settings, enabled tools, shortcuts and channel sets to a file"
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(export_dict(context), f, indent=1)
        self.report({'INFO'}, "Settings exported")
        return {'FINISHED'}


class MGE_OT_settings_import(bpy.types.Operator, ImportHelper):
    bl_idname = "mge.settings_import"
    bl_label = "Import Settings"
    bl_description = "Load settings exported from another machine"
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            with open(self.filepath, encoding="utf-8") as f:
                n = import_dict(context, json.load(f))
        except (OSError, ValueError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, "Imported %d setting(s)" % n)
        return {'FINISHED'}


classes = (MGE_OT_settings_export, MGE_OT_settings_import)
