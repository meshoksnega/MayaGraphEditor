"""Helpers to build real F-Curves in a headless `bpy` session (Blender 4.2+/5.x)."""
import bpy


def all_fcurves(action):
    """F-Curves of an action on both the legacy and the slotted-action API."""
    if hasattr(action, "layers"):
        out = []
        for layer in action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    out.extend(cb.fcurves)
        return out
    return list(action.fcurves)


def make_curve(points, path="location", index=0, obj_name="TestObj",
               handle='AUTO_CLAMPED', interpolation='BEZIER'):
    """Create an object, key `points` [(frame, value), ...] and return the F-Curve."""
    obj = bpy.data.objects.get(obj_name) or bpy.data.objects.new(obj_name, None)
    scene = bpy.context.scene
    if obj.name not in scene.collection.objects:
        scene.collection.objects.link(obj)
    for f, v in points:
        setattr_idx(obj, path, index, v)
        obj.keyframe_insert(path, index=index, frame=f)
    fc = [c for c in all_fcurves(obj.animation_data.action)
          if c.data_path == path and c.array_index == index][0]
    for k in fc.keyframe_points:
        k.handle_left_type = k.handle_right_type = handle
        k.interpolation = interpolation
    fc.update()
    return fc


def setattr_idx(obj, path, index, value):
    attr = getattr(obj, path)
    try:
        attr[index] = value
    except TypeError:
        setattr(obj, path, value)


def select_all(fc, state=True):
    for k in fc.keyframe_points:
        k.select_control_point = state
        k.select_left_handle = state
        k.select_right_handle = state
