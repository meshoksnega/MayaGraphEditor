"""Add-on shortcuts in the Graph Editor (rebindable in the add-on preferences).

Each tool's shortcuts exist only while the tool is enabled.
"""

import bpy

# tool -> [(operator idname, key, ctrl, shift, alt, {props})]
DEFAULTS = {
    "tangents": [("wm.call_menu_pie", 'V', False, False, True, {"name": "MGE_MT_tangent_pie"})],
    "ghost": [("mge.ghost_snapshot", 'B', True, False, True, {}),
              ("mge.ghost_swap", 'B', True, True, True, {})],
    "simplify": [("mge.simplify", 'X', True, False, True, {})],
    "retime": [("mge.retime", 'T', True, False, True, {})],
}
LABELS = {
    "wm.call_menu_pie": "Tangent pie menu",
    "mge.ghost_snapshot": "Ghost: snapshot",
    "mge.ghost_swap": "Ghost: swap",
    "mge.simplify": "Simplify selected keys",
    "mge.retime": "Retime selection",
}

_items = {}  # tool -> [(keymap, keymap_item)]


def add(tool):
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm else None
    if kc is None or tool in _items or tool not in DEFAULTS:
        return
    km = kc.keymaps.new(name="Graph Editor", space_type='GRAPH_EDITOR')
    made = []
    for idname, key, ctrl, shift, alt, props in DEFAULTS[tool]:
        kmi = km.keymap_items.new(idname, key, 'PRESS', ctrl=ctrl, shift=shift, alt=alt)
        for k, v in props.items():
            setattr(kmi.properties, k, v)
        made.append((km, kmi))
    _items[tool] = made


def remove(tool):
    for km, kmi in _items.pop(tool, []):
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass


def remove_all():
    for tool in list(_items):
        remove(tool)


def _matches(kmi, idname, props):
    if kmi.idname != idname:
        return False
    return all(getattr(kmi.properties, k, None) == v for k, v in props.items())


def draw_prefs(layout):
    """Rebindable list of our shortcuts (same widgets as Blender's keymap editor)."""
    import rna_keymap_ui
    box = layout.box()
    box.label(text="Shortcuts (Graph Editor)", icon='KEYINGSET')
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.user
    km = kc.keymaps.get("Graph Editor")
    if km is None or not _items:
        box.label(text="No tools with shortcuts are enabled")
        return
    col = box.column()
    for tool, entries in _items.items():
        for _km, addon_kmi in entries:
            props = next(d[5] for d in DEFAULTS[tool] if d[0] == addon_kmi.idname)
            for kmi in km.keymap_items:
                if _matches(kmi, addon_kmi.idname, props):
                    col.context_pointer_set("keymap", km)
                    rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)
                    break
