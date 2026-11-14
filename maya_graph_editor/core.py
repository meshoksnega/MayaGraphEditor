"""Settings, preferences and per-tool registration.

Each tool can be switched on/off independently (Preferences, or the
"Maya Tools" panel in the Graph Editor sidebar).  Switching a tool off
unregisters its operators, panel and draw handlers entirely.
"""

import bpy

from . import common, ghost, retime, simplify, tangents, updater

# Registration order == panel order (the panels also set bl_order).
TOOLS = (
    ("tangents", tangents, "One-Click Tangents"),
    ("ghost", ghost, "Buffer / Ghost Curve"),
    ("simplify", simplify, "Curve Simplify (live preview)"),
    ("retime", retime, "Retiming Lattice"),
)

_active = set()


@bpy.app.handlers.persistent
def _on_load_pre(_dummy=None):
    simplify.abort_session()
    retime.abort_session()


# --------------------------------------------------------------------------
# Tool registration
# --------------------------------------------------------------------------

def sync_tools():
    """Register / unregister tools to match the preferences."""
    for name, module, _label in TOOLS:
        want = common.tool_enabled(name)
        if want and name not in _active:
            for cls in module.classes:
                try:
                    bpy.utils.register_class(cls)
                except Exception:
                    common.log_exception("register %s" % cls.__name__)
            module.register_tool()
            _active.add(name)
        elif not want and name in _active:
            module.unregister_tool()
            for cls in reversed(module.classes):
                try:
                    bpy.utils.unregister_class(cls)
                except Exception:
                    pass
            _active.discard(name)
    common.redraw_graph_editors()
    return None  # when used as a timer: don't repeat


def _schedule_sync(_self=None, _context=None):
    # Defer: don't (un)register classes from inside a UI property callback.
    bpy.app.timers.register(sync_tools, first_interval=0.0)


# --------------------------------------------------------------------------
# Settings (stored in the .blend, per scene)
# --------------------------------------------------------------------------

def _tolerance_update(_self, context):
    simplify.on_tolerance_changed(context)


class MGE_Settings(bpy.types.PropertyGroup):
    ghost_show: bpy.props.BoolProperty(
        name="Show Ghost", default=True,
        description="Draw the stored ghost curves in the Graph Editor",
        update=lambda s, c: common.redraw_graph_editors())
    ghost_color: bpy.props.FloatVectorProperty(
        name="Ghost Color", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(0.55, 0.8, 1.0, 0.6),
        update=lambda s, c: common.redraw_graph_editors())
    ghost_width: bpy.props.FloatProperty(
        name="Line Width", default=1.5, min=0.5, max=8.0,
        update=lambda s, c: common.redraw_graph_editors())

    simplify_tolerance: bpy.props.FloatProperty(
        name="Tolerance", default=2.0, min=0.0, max=100.0, soft_max=25.0,
        precision=2, subtype='PERCENTAGE',
        description=("Largest allowed deviation from the original curve, as a "
                     "percentage of each curve's value range over the selected keys"),
        update=_tolerance_update)

    retime_ripple: bpy.props.BoolProperty(
        name="Ripple Later Keys", default=True,
        description=("Keys outside the selection (on the affected curves) move "
                     "along with the edge so they never collide with the retimed range"))
    retime_snap: bpy.props.BoolProperty(
        name="Snap To Whole Frames", default=False,
        description="Snap the dragged edge to whole frames (hold Ctrl for a temporary snap)")


# --------------------------------------------------------------------------
# Preferences + toggle panel
# --------------------------------------------------------------------------

def _draw_toggles(layout, prefs):
    col = layout.column(align=True)
    for name, _module, label in TOOLS:
        col.prop(prefs, "enable_" + name, text=label)


class MGE_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    enable_tangents: bpy.props.BoolProperty(
        name="One-Click Tangents", default=True, update=_schedule_sync)
    enable_ghost: bpy.props.BoolProperty(
        name="Buffer / Ghost Curve", default=True, update=_schedule_sync)
    enable_simplify: bpy.props.BoolProperty(
        name="Curve Simplify", default=True, update=_schedule_sync)
    enable_retime: bpy.props.BoolProperty(
        name="Retiming Lattice", default=True, update=_schedule_sync)

    update_auto_check: bpy.props.BoolProperty(
        name="Check for updates on startup",
        description="Ask GitHub for a newer release at most once a day (needs Online Access)",
        default=False)
    update_last_check: bpy.props.FloatProperty(default=0.0, options={'HIDDEN'})

    def draw(self, context):
        layout = self.layout
        layout.label(text="Tools (each can be switched off independently):")
        _draw_toggles(layout, self)
        layout.label(text="Find the tools in the Graph Editor sidebar (N) > Maya tab.")
        layout.separator()
        updater.draw_prefs(layout, self)


class MGE_PT_settings(bpy.types.Panel):
    bl_label = "Enabled Tools"
    bl_idname = "MGE_PT_settings"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 99
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context, fcurves_only=False)

    def draw(self, context):
        prefs = common.get_prefs()
        if prefs is None:
            self.layout.label(text="Preferences unavailable")
            return
        _draw_toggles(self.layout, prefs)
        updater.draw_sidebar_notice(self.layout)


_core_classes = (MGE_Settings, MGE_Preferences, MGE_PT_settings) + updater.classes


def register():
    for cls in _core_classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mge_settings = bpy.props.PointerProperty(type=MGE_Settings)
    if _on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load_pre)
    sync_tools()
    # Preferences may not be readable yet while the add-on is being enabled.
    bpy.app.timers.register(sync_tools, first_interval=0.2)
    bpy.app.timers.register(updater.maybe_auto_check, first_interval=5.0)


def unregister():
    for name, module, _label in reversed(TOOLS):
        if name in _active:
            module.unregister_tool()
            for cls in reversed(module.classes):
                try:
                    bpy.utils.unregister_class(cls)
                except Exception:
                    pass
    _active.clear()
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    if hasattr(bpy.types.Scene, "mge_settings"):
        del bpy.types.Scene.mge_settings
    for cls in reversed(_core_classes):
        bpy.utils.unregister_class(cls)
