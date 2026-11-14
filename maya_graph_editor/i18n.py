"""UI translations.

Blender translates labels, operator names and property names on its own once
they are registered here; switch language in Preferences > Interface >
Translation.  The table lives in i18n_data.py: to add a language, add a
column there (Blender locale code).  Missing entries stay in English.
"""

import bpy

from .i18n_data import LOCALES, TABLE

_CONTEXTS = ("*", "Operator")
# Older Blender versions name Simplified Chinese differently.
_ALIASES = {"zh_HANS": ("zh_CN",)}


def build():
    out = {}
    for col, loc in enumerate(LOCALES):
        table = {}
        for en, row in TABLE.items():
            text = row[col] if col < len(row) else ""
            if text:
                for ctx in _CONTEXTS:
                    table[(ctx, en)] = text
        out[loc] = table
        for alias in _ALIASES.get(loc, ()):
            out[alias] = table
    return out


def register():
    try:
        bpy.app.translations.register(__package__, build())
    except ValueError:  # already registered (reload)
        bpy.app.translations.unregister(__package__)
        bpy.app.translations.register(__package__, build())


def unregister():
    try:
        bpy.app.translations.unregister(__package__)
    except Exception:
        pass


def iface(text):
    """Translate a label built at runtime; use with str.format() templates."""
    return bpy.app.translations.pgettext_iface(text)
