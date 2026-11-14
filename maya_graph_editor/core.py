"""Settings, preferences and per-tool registration.

Each tool can be switched on/off independently (Preferences, or the
"Maya Tools" panel in the Graph Editor sidebar).  Switching a tool off
unregisters its operators, panel and draw handlers entirely.
"""

import bpy

from . import (cleanup, common, curves, ghost, keymaps, retime, simplify, slider, smooth, stats,
               tangents, tween, updater, warp)

# Registration order == panel order (the panels also set bl_order).
TOOLS = (
    ("tangents", tangents, "One-Click Tangents"),
    ("ghost", ghost, "Buffer / Ghost Curve"),
    ("simplify", simplify, "Curve Simplify (live preview)"),
    ("retime", retime, "Retiming Lattice"),
    ("curves", curves, "Curves (Infinity, Euler Filter)"),
    ("stats", stats, "Key Stats (frame / value fields)"),
    ("tween", tween, "Tween / Breakdown slider"),
    ("smooth", smooth, "Smooth (live preview)"),
    ("warp", warp, "Time Warp (ease timing)"),
    ("cleanup", cleanup, "Mocap Cleanup (bake, simplify, tangents)"),
)

_active = set()


@bpy.app.handlers.persistent
def _on_load_pre(_dummy=None):
    simplify.abort_session()
    retime.abort_session()
    slider.abort_session()


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
            keymaps.add(name)
            _active.add(name)
        elif not want and name in _active:
            keymaps.remove(name)
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


def _redraw(_self=None, _context=None):
    common.redraw_graph_editors()


_GHOST_COLORS = {"a": (0.55, 0.8, 1.0, 0.6), "b": (1.0, 0.6, 0.25, 0.6), "c": (0.55, 1.0, 0.5, 0.6)}


class MGE_Settings(bpy.types.PropertyGroup):
    # --- tangents
    tangent_side: bpy.props.EnumProperty(
        name="Side", items=tangents.SIDES, default='BOTH',
        description="Which tangent the buttons change (Ctrl+click: In, Alt+click: Out)")
    new_key_tangent: bpy.props.EnumProperty(
        name="New Keys", items=[(i, l, d) for i, l, d, _ip, _h in tangents.NEW_KEY_TYPES],
        get=tangents.get_new_key_type, set=tangents.set_new_key_type,
        description="Tangent of newly inserted keyframes (Blender's Preferences > Animation setting)")

    # --- ghost
    ghost_slot: bpy.props.EnumProperty(
        name="Slot", items=[('A', "A", "Ghost slot A"), ('B', "B", "Ghost slot B"),
                            ('C', "C", "Ghost slot C")], default='A',
        description="Slot used by Snapshot / Swap / Clear")
    ghost_show: bpy.props.BoolProperty(
        name="Show Ghosts", default=True,
        description="Draw the stored ghost curves in the Graph Editor", update=_redraw)
    ghost_show_a: bpy.props.BoolProperty(name="Show A", default=True, update=_redraw)
    ghost_show_b: bpy.props.BoolProperty(name="Show B", default=True, update=_redraw)
    ghost_show_c: bpy.props.BoolProperty(name="Show C", default=True, update=_redraw)
    ghost_color_a: bpy.props.FloatVectorProperty(
        name="Color A", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=_GHOST_COLORS["a"], update=_redraw)
    ghost_color_b: bpy.props.FloatVectorProperty(
        name="Color B", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=_GHOST_COLORS["b"], update=_redraw)
    ghost_color_c: bpy.props.FloatVectorProperty(
        name="Color C", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=_GHOST_COLORS["c"], update=_redraw)
    ghost_width: bpy.props.FloatProperty(
        name="Line Width", default=1.5, min=0.5, max=8.0, update=_redraw)
    ghost_style: bpy.props.EnumProperty(
        name="Style", items=[('SOLID', "Solid", ""), ('DASHED', "Dashed", "")],
        default='SOLID', update=_redraw)
    ghost_range: bpy.props.EnumProperty(
        name="Ghost Range",
        items=[('KEYS', "Key Range", "From the first to the last key of each curve"),
               ('SCENE', "Scene Range", "The scene (or preview) frame range, including "
                                        "extrapolation and cycles")],
        default='KEYS', description="Frames covered by new snapshots")
    ghost_save: bpy.props.BoolProperty(
        name="Save Ghosts in File", default=True,
        description="Keep the ghosts when the .blend is saved and reopened")

    # --- key stats
    stats_mode: bpy.props.EnumProperty(
        name="Mode", items=[('ABSOLUTE', "Absolute", "Show and set actual frame / value"),
                            ('RELATIVE', "Relative", "Offset the selection by the number typed")],
        default='ABSOLUTE')
    stats_frame: bpy.props.FloatProperty(
        name="Frame", get=stats.get_frame, set=stats.set_frame, precision=2,
        description="Absolute: first selected frame (moves the whole selection). Relative: offset")
    stats_value: bpy.props.FloatProperty(
        name="Value", get=stats.get_value, set=stats.set_value, precision=3,
        description="Absolute: value of every selected key. Relative: offset")

    # --- tween / smooth / warp
    tween_bias: bpy.props.FloatProperty(
        name="Tween", default=50.0, min=-50.0, max=150.0, precision=0, subtype='PERCENTAGE',
        description="0% = previous key, 100% = next key, beyond = overshoot",
        update=lambda s, c: slider.on_value_changed("tween", c))
    smooth_sigma: bpy.props.FloatProperty(
        name="Blur", default=2.0, min=0.0, max=20.0, precision=1,
        description="Width of the smoothing, in frames",
        update=lambda s, c: slider.on_value_changed("smooth", c))
    warp_amount: bpy.props.FloatProperty(
        name="Amount", default=50.0, min=0.0, max=100.0, precision=0, subtype='PERCENTAGE',
        description="Blend from linear timing (0%) to the full easing (100%)",
        update=lambda s, c: slider.on_value_changed("warp", c))
    warp_shape: bpy.props.EnumProperty(
        name="Shape", items=[('EASE_IN', "Ease In", "Slow in: keys bunch up at the start"),
                             ('EASE_OUT', "Ease Out", "Slow out: keys bunch up at the end"),
                             ('EASE_IN_OUT', "In/Out", "Slow in and out")],
        default='EASE_IN_OUT')

    # --- mocap cleanup
    cleanup_bake: bpy.props.BoolProperty(
        name="Bake to Every Frame", default=True,
        description="Resample the selected range to a key on every whole frame first")
    cleanup_tolerance: bpy.props.FloatProperty(
        name="Tolerance", default=1.0, min=0.0, max=100.0, soft_max=25.0, precision=2,
        subtype='PERCENTAGE',
        description="Largest allowed deviation, as a percentage of each curve's value range")
    cleanup_tangent: bpy.props.EnumProperty(
        name="Tangents", items=cleanup.TANGENT_ITEMS, default='CLAMPED')

    # --- retime
    retime_percent: bpy.props.FloatProperty(
        name="Scale", default=100.0, min=1.0, soft_max=400.0, subtype='PERCENTAGE',
        description="Stretch the retime range to this percentage of its length")
    retime_anchor: bpy.props.EnumProperty(
        name="Anchor", items=[('LEFT', "Start", "Keep the first selected key in place"),
                              ('CENTER', "Center", "Scale about the middle of the range"),
                              ('RIGHT', "End", "Keep the last selected key in place")],
        default='LEFT')

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
    enable_curves: bpy.props.BoolProperty(
        name="Curves", default=True, update=_schedule_sync)
    enable_stats: bpy.props.BoolProperty(
        name="Key Stats", default=True, update=_schedule_sync)
    enable_tween: bpy.props.BoolProperty(
        name="Tween", default=True, update=_schedule_sync)
    enable_smooth: bpy.props.BoolProperty(
        name="Smooth", default=True, update=_schedule_sync)
    enable_warp: bpy.props.BoolProperty(
        name="Time Warp", default=True, update=_schedule_sync)
    enable_cleanup: bpy.props.BoolProperty(
        name="Mocap Cleanup", default=True, update=_schedule_sync)
    use_theme_colors: bpy.props.BoolProperty(
        name="Use theme colours for on-screen bars and the lattice", default=True,
        update=_redraw)
    show_header_tangents: bpy.props.BoolProperty(
        name="Tangent buttons in the Graph Editor header", default=False, update=_redraw,
        description="Also show the six tangent buttons as icons in the Graph Editor header")

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
        layout.prop(self, "show_header_tangents")
        layout.prop(self, "use_theme_colors")
        layout.separator()
        keymaps.draw_prefs(layout)
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


_core_classes = (MGE_Settings, MGE_Preferences, MGE_PT_settings) + updater.classes + \
    slider.core_classes


def register():
    for cls in _core_classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mge_settings = bpy.props.PointerProperty(type=MGE_Settings)
    if _on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load_pre)
    updater.restore_message()
    sync_tools()
    # Preferences may not be readable yet while the add-on is being enabled.
    bpy.app.timers.register(sync_tools, first_interval=0.2)
    bpy.app.timers.register(updater.maybe_auto_check, first_interval=5.0)


def unregister():
    keymaps.remove_all()
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
