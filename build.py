#!/usr/bin/env python3
"""Build the installable zips into ./dist

  maya_graph_editor-<ver>.zip         Blender 4.2+ Extension layout (manifest at the zip root)
                                      Preferences > Get Extensions > (v) > Install from Disk
  maya_graph_editor-<ver>-legacy.zip  classic add-on layout (folder inside the zip)
                                      Preferences > Add-ons > Install from Disk (older Blender / legacy)
"""
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).parent
PKG = ROOT / "maya_graph_editor"
DIST = ROOT / "dist"

version = re.search(r'^version = "([^"]+)"', (PKG / "blender_manifest.toml").read_text(), re.M).group(1)
files = sorted(p for p in PKG.rglob("*") if p.is_file() and "__pycache__" not in p.parts
               and p.suffix != ".pyc")

DIST.mkdir(exist_ok=True)
ext = DIST / ("maya_graph_editor-%s.zip" % version)
leg = DIST / ("maya_graph_editor-%s-legacy.zip" % version)
with zipfile.ZipFile(ext, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(f, f.relative_to(PKG).as_posix())
with zipfile.ZipFile(leg, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        if f.name != "blender_manifest.toml":
            z.write(f, "maya_graph_editor/" + f.relative_to(PKG).as_posix())
print("built", ext.name, "and", leg.name)
