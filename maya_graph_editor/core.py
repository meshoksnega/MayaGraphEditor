"""Settings, preferences and registration.

Every tool is registered once, when the add-on is enabled, and unregistered
when it is disabled.  Switching a single tool off (Preferences, or the
"Enabled Tools" panel in the sidebar) hides its panel and makes its
operators, shortcuts and overlays do nothing: their poll() and draw
callbacks check the preference.  Nothing is registered later, and the
add-on runs no background timers.
"""

import bpy

from . import (blocking, channels, cleanup, common, curves, generate, ghost, hub, i18n, keymaps,
               presets, retime, shapes, simplify, slider, smooth, stacked, stagger, stats,
               tangents, tween, updater, warp, whatsnew)

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
    ("blocking", blocking, "Blocking (stepped preview, round, loop)"),
    ("stagger", stagger, "Stagger / Overlap"),
    ("hub", hub, "Key Sliders (Blender's slider tools)"),
    ("channels", channels, "Channels & Selection"),
    ("generate", generate, "Noise / Settle"),
    ("shapes", shapes, "Shapes & Paste"),
    ("stacked", stacked, "Stacked Overview (experimental)"),
)

_registered = []   # tool names, in registration order


@bpy.app.handlers.persistent
def _on_load_pre(_dummy=None):
    simplify.abort_session()
    retime.abort_session()
    slider.abort_session()


# --------------------------------------------------------------------------
# Tool on/off
# --------------------------------------------------------------------------

def _gate(cls, tool):
    """Make cls.poll() return False while `tool` is switched off.

    Hides panels and menus, and turns operators (buttons, F3 search and
    shortcuts) into no-ops, without registering or unregistering anything."""
    if cls.__dict__.get("_mge_tool") == tool:
        return  # already gated (add-on enabled a second time this session)
    cls.poll = classmethod(_gated_poll(getattr(cls, "poll", None), tool))
    cls._mge_tool = tool


def _gated_poll(base, tool):
    # Blender requires poll(cls, context) exactly, so capture in a closure.
    # `base` is the original poll bound to the class (it may come from a mixin).
    def poll(cls, context):
        if not common.tool_enabled(tool):
            return False
        return base(context) if base is not None else True
    return poll


def _on_toggle(_self=None, _context=None):
    common.redraw_graph_editors()


# --------------------------------------------------------------------------
# Settings (stored in the .blend, per scene)
# --------------------------------------------------------------------------

def _tolerance_update(_self, context):
    simplify.on_tolerance_changed(context)


def _redraw(_self=None, _context=None):
    common.redraw_graph_editors()


# Neutral grey like Maya's buffer curve, then orange and magenta: none of them
# can be mistaken for Blender's red / green / blue X, Y, Z channel colours.
_GHOST_COLORS = {"a": (0.85, 0.85, 0.85, 0.55), "b": (1.0, 0.55, 0.15, 0.65),
                 "c": (0.95, 0.35, 0.95, 0.65)}


class MGE_ChannelSet(bpy.types.PropertyGroup):
    data: bpy.props.StringProperty()   # JSON list of [data_path, array_index]


class MGE_Settings(bpy.types.PropertyGroup):
    # --- blocking
    round_auto: bpy.props.BoolProperty(
        name="Auto Round", default=False,
        description="Round keys to whole frames after Retime / Region, Time Warp and Stagger")

    # --- stagger / overlap
    stagger_group: bpy.props.EnumProperty(
        name="Group", items=[('BONE', "Per Bone / Object", "Curves of one bone or object move together"),
                             ('CURVE', "Each Curve", "Every curve is its own step")], default='BONE')
    stagger_order: bpy.props.EnumProperty(
        name="Order", items=[('CHANNEL', "Channel List Order", "Top to bottom as listed in the editor"),
                             ('HIERARCHY', "Bone Hierarchy", "From the root bone towards the tips")],
        default='CHANNEL')
    stagger_reverse: bpy.props.BoolProperty(name="Reverse Order", default=False)
    stagger_offset: bpy.props.FloatProperty(
        name="Offset", default=2.0, min=-12.0, max=12.0, precision=1,
        description="Frames each step is shifted after the one before it",
        update=lambda s, c: slider.on_value_changed("stagger", c))
    stagger_gain: bpy.props.FloatProperty(
        name="Gain per Step", default=100.0, min=10.0, max=200.0, precision=0, subtype='PERCENTAGE',
        description="Scale each step's values by this much more than the step before")
    overlap_delay: bpy.props.FloatProperty(
        name="Delay", default=2.0, min=0.0, max=12.0, precision=1,
        description="Frames each follower lags behind the one before it",
        update=lambda s, c: slider.on_value_changed("overlap", c))
    overlap_gain: bpy.props.FloatProperty(
        name="Gain per Bone", default=90.0, min=10.0, max=200.0, precision=0, subtype='PERCENTAGE',
        description="How much of the motion each follower keeps from the one before it")

    # --- channels
    channel_sets: bpy.props.CollectionProperty(type=MGE_ChannelSet)
    select_nth: bpy.props.IntProperty(name="N", default=2, min=2, max=100)

    # --- ghost extras
    ghost_source: bpy.props.PointerProperty(
        name="Source Action", type=bpy.types.Action,
        description="Action whose matching channels are shown as ghosts (reference, mocap, earlier take)")

    # --- noise / settle
    noise_amount: bpy.props.FloatProperty(
        name="Amount", default=5.0, min=0.0, max=50.0, precision=1, subtype='PERCENTAGE',
        description="Noise size as a percentage of each curve's value range",
        update=lambda s, c: slider.on_value_changed("noise", c))
    noise_scale: bpy.props.FloatProperty(
        name="Scale", default=6.0, min=0.5, max=200.0, precision=1,
        description="Frames per wiggle")
    noise_seed: bpy.props.IntProperty(name="Seed", default=1, min=0)
    settle_amount: bpy.props.FloatProperty(
        name="Amount", default=100.0, min=0.0, max=200.0, precision=0, subtype='PERCENTAGE',
        description="Size of the wobble (100% matches the incoming speed)",
        update=lambda s, c: slider.on_value_changed("settle", c))
    settle_period: bpy.props.FloatProperty(
        name="Wobble", default=8.0, min=2.0, max=60.0, precision=0,
        description="Frames per wobble")
    settle_length: bpy.props.FloatProperty(
        name="Length", default=24.0, min=4.0, max=240.0, precision=0,
        description="Frames until the motion has come to rest")

    # --- shapes / paste
    shape_active: bpy.props.EnumProperty(name="Shape", items=shapes.enum_items)
    paste_relative: bpy.props.BoolProperty(
        name="Relative Values", default=False,
        description="Offset pasted values so they start from the curve's current value")

    # --- stacked overview
    stacked_show: bpy.props.BoolProperty(name="Stacked Overview", default=False, update=_redraw)

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
                              ('RIGHT', "End", "Keep the last selected key in place"),
                              ('PLAYHEAD', "Playhead", "Scale about the current frame")],
        default='LEFT')
    retime_scope: bpy.props.EnumProperty(
        name="Scope",
        items=[('SELECTED', "Selected Keys", "The selected keys of the curves shown"),
               ('RIG', "Whole Rig", "Every key of the selected objects (selected bones in Pose "
                                    "Mode) inside the selection's time range, shown or not")],
        default='SELECTED')
    retime_length: bpy.props.FloatProperty(
        name="Length", default=24.0, min=0.01, precision=1,
        description="Target length in frames")
    region_values: bpy.props.BoolProperty(
        name="Value Handles", default=True,
        description="Show top/bottom edges and corners to scale values in the lattice")
    region_value_percent: bpy.props.FloatProperty(
        name="Value Scale", default=100.0, soft_min=-200.0, soft_max=400.0, subtype='PERCENTAGE',
        description="Scale the selected keys' values by this percentage about the pivot")
    region_pivot: bpy.props.EnumProperty(
        name="Pivot", items=[('ZERO', "Zero", "Scale about value 0"),
                             ('FIRST', "First Key", "Scale about each curve's first selected key"),
                             ('LAST', "Last Key", "Scale about each curve's last selected key"),
                             ('CENTER', "Center", "Scale about the middle of each curve's selection")],
        default='CENTER')

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
        name="One-Click Tangents", default=True, update=_on_toggle)
    enable_ghost: bpy.props.BoolProperty(
        name="Buffer / Ghost Curve", default=True, update=_on_toggle)
    enable_simplify: bpy.props.BoolProperty(
        name="Curve Simplify", default=True, update=_on_toggle)
    enable_retime: bpy.props.BoolProperty(
        name="Retiming Lattice", default=True, update=_on_toggle)
    enable_curves: bpy.props.BoolProperty(
        name="Curves", default=True, update=_on_toggle)
    enable_stats: bpy.props.BoolProperty(
        name="Key Stats", default=True, update=_on_toggle)
    enable_tween: bpy.props.BoolProperty(
        name="Tween", default=True, update=_on_toggle)
    enable_smooth: bpy.props.BoolProperty(
        name="Smooth", default=True, update=_on_toggle)
    enable_warp: bpy.props.BoolProperty(
        name="Time Warp", default=True, update=_on_toggle)
    enable_cleanup: bpy.props.BoolProperty(
        name="Mocap Cleanup", default=True, update=_on_toggle)
    enable_blocking: bpy.props.BoolProperty(name="Blocking", default=True, update=_on_toggle)
    enable_stagger: bpy.props.BoolProperty(name="Stagger / Overlap", default=True, update=_on_toggle)
    enable_hub: bpy.props.BoolProperty(name="Key Sliders", default=True, update=_on_toggle)
    enable_channels: bpy.props.BoolProperty(name="Channels", default=True, update=_on_toggle)
    enable_generate: bpy.props.BoolProperty(name="Noise / Settle", default=True, update=_on_toggle)
    enable_shapes: bpy.props.BoolProperty(name="Shapes & Paste", default=True, update=_on_toggle)
    enable_stacked: bpy.props.BoolProperty(name="Stacked Overview", default=True, update=_on_toggle)
    hud_scale: bpy.props.FloatProperty(
        name="On-Screen Text Size", default=1.0, min=0.8, max=2.5, step=10, precision=1,
        description="Size of the text in the add-on's on-screen bars, lattice and overviews",
        update=_redraw)
    show_whats_new: bpy.props.BoolProperty(
        name="Show What's New after an update", default=True,
        description="After an update, show a short note in the Maya tab with a link to what changed")
    last_seen_version: bpy.props.StringProperty(default="", options={'HIDDEN'})
    use_theme_colors: bpy.props.BoolProperty(
        name="Use theme colours for on-screen bars and the lattice", default=True,
        update=_redraw)
    show_header_tangents: bpy.props.BoolProperty(
        name="Tangent buttons in the Graph Editor header", default=False, update=_redraw,
        description="Also show the six tangent buttons as icons in the Graph Editor header")


    def draw(self, context):
        layout = self.layout
        layout.label(text="Tools (each can be switched off independently):")
        _draw_toggles(layout, self)
        layout.label(text="Find the tools in the Graph Editor sidebar (N) > Maya tab.")
        layout.prop(self, "show_header_tangents")
        layout.prop(self, "use_theme_colors")
        layout.prop(self, "hud_scale")
        row = layout.row(align=True)
        row.operator("mge.settings_export", icon='EXPORT')
        row.operator("mge.settings_import", icon='IMPORT')
        whatsnew.draw_notice(layout)
        row = layout.row(align=True)
        row.prop(self, "show_whats_new")
        row.operator("mge.whats_new", text="What's New", icon='INFO')
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
        whatsnew.draw_notice(self.layout)
        _draw_toggles(self.layout, prefs)
        updater.draw_sidebar_notice(self.layout)


_core_classes = (MGE_ChannelSet, MGE_Settings, MGE_Preferences, MGE_PT_settings) + \
    updater.classes + slider.core_classes + whatsnew.classes + presets.classes


def register():
    for cls in _core_classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mge_settings = bpy.props.PointerProperty(type=MGE_Settings)
    i18n.register()
    if _on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load_pre)
    updater.restore_message()
    for name, module, _label in TOOLS:
        for cls in module.classes:
            _gate(cls, name)
            bpy.utils.register_class(cls)
        module.register_tool()
        keymaps.add(name)
        _registered.append(name)
    whatsnew.remember_first_install()


def unregister():
    i18n.unregister()
    keymaps.remove_all()
    for name, module, _label in reversed(TOOLS):
        if name not in _registered:
            continue
        module.unregister_tool()
        for cls in reversed(module.classes):
            bpy.utils.unregister_class(cls)
    _registered.clear()
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    if hasattr(bpy.types.Scene, "mge_settings"):
        del bpy.types.Scene.mge_settings
    for cls in reversed(_core_classes):
        bpy.utils.unregister_class(cls)
