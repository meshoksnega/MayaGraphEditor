bl_info = {
    "name": "Maya Graph Editor Tools",
    "author": "meshoksnega",
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "Graph Editor > Sidebar (N) > Maya",
    "description": ("Maya-style Graph Editor comforts: buffer/ghost curve, "
                    "one-click tangents, live curve simplify, retiming lattice"),
    "category": "Animation",
}

if "bpy" in locals():  # support Blender's "Reload Scripts"
    import importlib
    for _m in ("common", "simplify_core", "ghost", "tangents", "simplify",
               "retime", "curves", "stats", "keymaps", "updater", "core"):
        if _m in locals():
            importlib.reload(locals()[_m])

import bpy  # noqa: E402,F401
from . import (common, simplify_core, ghost, tangents, simplify, retime,  # noqa: E402,F401
               curves, stats, keymaps, updater, core)


def register():
    core.register()


def unregister():
    core.unregister()
