"""Stand-in for the GitHub updater in the extensions.blender.org build.

Blender's extension platform updates add-ons itself and doesn't allow them
to update themselves, so this build ships without any network code.
"""

classes = ()


def restore_message():
    pass


def draw_prefs(layout, prefs):
    pass


def draw_sidebar_notice(layout):
    pass
