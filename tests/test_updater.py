"""Updater tests (python tests/test_updater.py with a `bpy` Python).

Pure parsing/selection logic offline, plus one live call to the GitHub API
(skipped when offline) and Blender's own installer on the built zip.
"""
import os
import sys
import types

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from maya_graph_editor import updater  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


print("version parsing")
check(updater.parse_version("v1.2.3") == (1, 2, 3), "v1.2.3")
check(updater.parse_version("1.4") == (1, 4, 0), "1.4")
check(updater.parse_version("2.0.1-beta") == (2, 0, 1), "2.0.1-beta")
check(updater.parse_version("latest") is None, "non-version tag")
check(updater.parse_version("v1.10.0") > updater.parse_version("v1.9.9"), "numeric, not text, comparison")
import re  # noqa: E402
_manifest = open(os.path.join(HERE, "..", "maya_graph_editor", "blender_manifest.toml")).read()
check(updater.current_version() == updater.parse_version(re.search(r'^version = "([^"]+)"', _manifest, re.M).group(1)),
      "installed version read from manifest")

print("asset selection")
assets = [{"name": "maya_graph_editor-1.1.0-legacy.zip", "browser_download_url": "L"},
          {"name": "maya_graph_editor-1.1.0.zip", "browser_download_url": "E", "digest": "sha256:ab"},
          {"name": "notes.txt"}]
check(updater.pick_asset(assets, "EXTENSION")["browser_download_url"] == "E", "extension zip for extensions")
check(updater.pick_asset(assets, "LEGACY")["browser_download_url"] == "L", "legacy zip for legacy installs")
check(updater.pick_asset([{"name": "x.zip"}], "LEGACY")["name"] == "x.zip", "single zip fallback")
check(updater.pick_asset([{"name": "a.txt"}], "EXTENSION") is None, "no zip -> None")
info = updater.parse_release({"tag_name": "v1.1.0", "html_url": "U", "assets": assets}, "EXTENSION")
check(info["version"] == (1, 1, 0) and info["asset_url"] == "E" and info["digest"] == "sha256:ab",
      "release JSON parsed")
check(updater.asset_version("maya_graph_editor-1.1.0.zip") == (1, 1, 0), "version from zip name")
check(updater.asset_version("maya_graph_editor-1.1.0-legacy.zip") == (1, 1, 0), "version from legacy zip name")
check(updater.asset_version("maya_graph_editor.zip") is None, "zip without version")
odd_tag = updater.parse_release({"tag_name": "0.0.3", "assets": assets}, "EXTENSION")
check(odd_tag["version"] == (1, 1, 0), "zip version wins over a differently numbered tag (0.0.3)")
no_ver = updater.parse_release({"tag_name": "v2.0", "assets": [{"name": "addon.zip"}]}, "EXTENSION")
check(no_ver["version"] == (2, 0, 0), "falls back to the tag when the zip has no version")
check(updater.install_kind() == ("LEGACY", None), "plain package name -> legacy install")
updater.common.PKG = "bl_ext.user_default.maya_graph_editor"
check(updater.install_kind() == ("EXTENSION", "user_default"), "bl_ext.<repo>.<id> -> extension in that repo")
updater.common.PKG = "maya_graph_editor"

print("check worker outcomes (network stubbed)")
orig = updater.fetch_latest
updater.fetch_latest = lambda kind: dict(info)
updater._check_worker((1, 0, 0), "EXTENSION")
check(updater.get_state()["status"] == "AVAILABLE", "newer release -> AVAILABLE")
updater._check_worker((1, 1, 0), "EXTENSION")
check(updater.get_state()["status"] == "UP_TO_DATE", "same version -> UP_TO_DATE")
updater.fetch_latest = lambda kind: dict(info, asset_url=None, asset_name=None)
updater._check_worker((1, 0, 0), "EXTENSION")
check(updater.get_state()["status"] == "ERROR" and "no installable zip" in updater.get_state()["message"],
      "release without zip -> clear error")


def boom(kind):
    raise RuntimeError("No release has been published on GitHub yet")


updater.fetch_latest = boom
updater._check_worker((1, 0, 0), "EXTENSION")
check(updater.get_state()["status"] == "ERROR", "network error -> ERROR, no exception")
updater.fetch_latest = orig

print("live GitHub API")
try:
    live = updater.fetch_latest("EXTENSION")
    print("  latest release:", live["tag"], live["asset_name"])
    check(live["version"] is not None, "live release parsed")
except RuntimeError as e:
    print("  (%s)" % e)
    check("No release" in str(e) or "reach" in str(e), "live call handled: %s" % e)

print("checksum verification")
import hashlib, http.server, threading, tempfile  # noqa: E401,E402
payload = b"PK-fake-zip-bytes" * 100
tmp = tempfile.mkdtemp()
with open(os.path.join(tmp, "a.zip"), "wb") as f:
    f.write(payload)
handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=tmp, **k)  # noqa: E731
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/a.zip" % srv.server_address[1]
good = {"asset_url": url, "asset_name": "a.zip", "tag": "v9", "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1"
updater._download_worker(good)
st = updater.get_state()
check(st["zip_path"] and open(st["zip_path"], "rb").read() == payload, "download saved, checksum accepted")
updater._set(zip_path=None)
updater._download_worker(dict(good, digest="sha256:" + "0" * 64))
check(updater.get_state()["status"] == "ERROR" and "checksum" in updater.get_state()["message"],
      "bad checksum rejected")
srv.shutdown()

print("Blender's installer accepts the built extension zip")
import glob  # noqa: E402
_zips = [z for z in glob.glob(os.path.join(HERE, "..", "dist", "maya_graph_editor-*.zip")) if "legacy" not in z]
zip_path = sorted(_zips)[-1] if _zips else ""
repos = [r.module for r in bpy.context.preferences.extensions.repos if not r.use_remote_url]
print("  local repos:", repos)
if os.path.exists(zip_path) and repos:
    res = bpy.ops.extensions.package_install_files(filepath=os.path.abspath(zip_path), repo=repos[0],
                                                   enable_on_install=False, overwrite=True)
    check(res == {'FINISHED'}, "package_install_files -> %s" % res)
else:
    print("  (skipped: build first / no local repo)")

print()
print("FAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
