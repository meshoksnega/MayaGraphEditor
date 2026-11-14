"""Tool - Key Sliders hub.

Blender already has a good set of interactive key sliders, but they live
three menus deep (Key > Blend / Smooth).  This panel puts them one click
away.  They are Blender's own operators, started in the main Graph Editor
region so their on-screen slider appears where you expect it.
"""

import bpy

from . import common

# (operator name in bpy.ops.graph, label, icon)
SLIDERS = (
    ("breakdown", "Breakdown", 'IPO_EASE_IN_OUT'),
    ("blend_to_neighbor", "Blend to Neighbor", 'ARROW_LEFTRIGHT'),
    ("blend_to_default", "Blend to Default", 'LOOP_BACK'),
    ("ease", "Ease", 'IPO_EASE_IN'),
    ("blend_to_ease", "Blend to Ease", 'IPO_QUAD'),
    ("blend_offset", "Blend Offset", 'NEXT_KEYFRAME'),
    ("push_pull", "Push / Pull", 'FULLSCREEN_ENTER'),
    ("scale_average", "Scale Average", 'FULLSCREEN_EXIT'),
    ("scale_from_neighbor", "Scale from Neighbor", 'PIVOT_BOUNDBOX'),
    ("shear", "Shear", 'MOD_LATTICE'),
    ("match_slope", "Match Slope", 'IPO_LINEAR'),
    ("time_offset", "Time Offset", 'TIME'),
    ("gaussian_smooth", "Gaussian Smooth", 'SMOOTHCURVE'),
    ("butterworth_smooth", "Butterworth Smooth", 'MOD_SMOOTH'),
)


def available():
    return [s for s in SLIDERS if hasattr(bpy.ops.graph, s[0])]


class MGE_OT_blender_slider(bpy.types.Operator):
    bl_idname = "mge.blender_slider"
    bl_label = "Key Slider"
    bl_description = "Start one of Blender's interactive key sliders on the selected keys"
    bl_options = {'INTERNAL'}

    name: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context) and common.modal_owner() is None

    @classmethod
    def description(cls, context, properties):
        for name, label, _icon in SLIDERS:
            if name == properties.name:
                return "%s (Blender's slider): drag, click to apply, right-click to cancel" % label
        return cls.bl_description

    def execute(self, context):
        if self.name not in {s[0] for s in available()}:
            self.report({'WARNING'}, "Not available in this Blender version")
            return {'CANCELLED'}
        region = common.window_region(context.area)
        op = getattr(bpy.ops.graph, self.name)
        try:
            with context.temp_override(region=region):
                if not op.poll():
                    self.report({'WARNING'}, "Select keyframes first")
                    return {'CANCELLED'}
                op('INVOKE_DEFAULT')
        except RuntimeError as e:
            self.report({'WARNING'}, str(e).strip().splitlines()[-1])
            return {'CANCELLED'}
        return {'FINISHED'}


class MGE_PT_hub(bpy.types.Panel):
    bl_label = "Key Sliders"
    bl_idname = "MGE_PT_hub"
    bl_space_type = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Maya"
    bl_order = 12
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return common.graph_poll(context)

    def draw(self, context):
        grid = self.layout.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        for name, label, icon in available():
            grid.operator("mge.blender_slider", text=label, icon=icon).name = name


classes = (MGE_OT_blender_slider, MGE_PT_hub)


def register_tool():
    pass


def unregister_tool():
    pass
