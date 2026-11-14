#!/usr/bin/env python3
"""Build the installable zips into ./dist

  maya_graph_editor-<ver>.zip         Blender 4.2+ Extension layout (manifest at the zip root)
                                      Preferences > Get Extensions > (v) > Install from Disk
  maya_graph_editor-<ver>-legacy.zip  classic add-on layout (folder inside the zip)
                                      Preferences > Add-ons > Install from Disk (older Blender / legacy)

  python build.py --store   also writes dist/store/maya_graph_editor-<ver>-extensions.zip:
                            the build to submit to extensions.blender.org (no GitHub updater,
                            no network permission)
"""
import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).parent
PKG = ROOT / "maya_graph_editor"
DIST = ROOT / "dist"

version = re.search(r'^version = "([^"]+)"', (PKG / "blender_manifest.toml").read_text(), re.M).group(1)
bl_version = re.search(r'"version": \((\d+), (\d+), (\d+)\)', (PKG / "__init__.py").read_text())
if ".".join(bl_version.groups()) != version:
    raise SystemExit("version mismatch: blender_manifest.toml says %s, bl_info says %s"
                     % (version, ".".join(bl_version.groups())))
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

if "--store" in sys.argv:
    # Build for extensions.blender.org: no self-updater, no network permission.
    # Kept out of dist/*.zip so it is never attached to a GitHub release.
    store_dir = DIST / "store"
    store_dir.mkdir(exist_ok=True)
    store = store_dir / ("maya_graph_editor-%s-extensions.zip" % version)
    manifest = (PKG / "blender_manifest.toml").read_text()
    manifest = re.sub(r"\n\[permissions\]\n(?:[^\[\n][^\n]*\n?)*", "\n", manifest).rstrip() + "\n"
    with zipfile.ZipFile(store, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            if f.name == "updater.py":
                z.write(ROOT / "store" / "updater.py", "updater.py")
            elif f.name == "blender_manifest.toml":
                z.writestr("blender_manifest.toml", manifest)
            else:
                z.write(f, f.relative_to(PKG).as_posix())
    print("built", "store/" + store.name, "(no updater, no network permission)")
