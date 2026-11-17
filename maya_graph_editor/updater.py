"""Update the add-on from the latest GitHub release.

* Check (only when you click Check for Updates): asks the GitHub API for the
  latest published release of REPO and
  compares its tag (``v1.2.0`` / ``1.2.0``) with the installed version.
* Install: downloads the matching release asset (the Extension zip, or the
  ``-legacy.zip`` for a legacy add-on install), verifies its SHA-256 when
  GitHub provides one, and hands it to Blender's own installer.

Network access happens on a worker thread (Blender never freezes) and only
when Blender's "Allow Online Access" preference is on.  While a check or
download is running, a short timer collects the result; nothing runs
otherwise.
"""

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request

import bpy

from . import common

REPO = "meshoksnega/MayaGraphEditor"
API_LATEST = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES_PAGE = "https://github.com/%s/releases" % REPO
USER_AGENT = "maya-graph-editor-updater"
MAX_DOWNLOAD = 50 * 1024 * 1024
# Survives the add-on reloading itself during an update.
MARKER = os.path.join(tempfile.gettempdir(), "maya_graph_editor_update.json")

# Shared with the worker thread; only plain Python values in here.
_lock = threading.Lock()
_state = {
    "status": "IDLE",   # IDLE | CHECKING | UP_TO_DATE | AVAILABLE | DOWNLOADING | INSTALLED | ERROR
    "message": "",
    "latest": None,     # dict(version=tuple, tag=str, notes_url=str, asset_url=str, asset_name=str, digest=str)
    "zip_path": None,
}
_timer_running = False


# --------------------------------------------------------------------------
# Pure helpers (tested without network)
# --------------------------------------------------------------------------

def parse_version(text):
    """'v1.2.3', '1.2', '1.2.3-beta' -> (1, 2, 3) / (1, 2, 0); None if no numbers."""
    m = re.match(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(text))
    if not m:
        return None
    return tuple(int(g or 0) for g in m.groups())


def asset_version(name):
    """'maya_graph_editor-1.1.0-legacy.zip' -> (1, 1, 0); None if no version."""
    m = re.search(r"-v?(\d+)\.(\d+)(?:\.(\d+))?(?:-[A-Za-z]+)?\.zip$", name)
    return tuple(int(g or 0) for g in m.groups()) if m else None


def version_str(v):
    return ".".join(str(x) for x in v) if v else "?"


def current_version():
    """Installed version: the manifest (Extension) or bl_info (legacy)."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    manifest = os.path.join(pkg_dir, "blender_manifest.toml")
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as f:
            m = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M)
        if m:
            return parse_version(m.group(1))
    from . import bl_info
    return tuple(bl_info["version"])


def install_kind():
    """('EXTENSION', repo_module) for Blender 4.2+ extensions, else ('LEGACY', None)."""
    parts = common.PKG.split(".")
    if len(parts) == 3 and parts[0] == "bl_ext":
        return "EXTENSION", parts[1]
    return "LEGACY", None


def managed_by_blender():
    """Name of the remote extensions repository this add-on was installed from
    (e.g. extensions.blender.org), else None.  Such installs are updated by
    Blender itself, and the platform doesn't allow add-ons to update themselves,
    so the GitHub updater switches off."""
    kind, repo = install_kind()
    if kind != "EXTENSION":
        return None
    try:
        for r in bpy.context.preferences.extensions.repos:
            if r.module == repo and r.use_remote_url:
                return r.name or r.remote_url
    except Exception:
        pass
    return None


def pick_asset(assets, kind):
    """Choose the zip to download from a release's asset list."""
    zips = [a for a in assets if a.get("name", "").lower().endswith(".zip")]
    legacy = [a for a in zips if "legacy" in a["name"].lower()]
    ext = [a for a in zips if "legacy" not in a["name"].lower()]
    preferred = legacy if kind == "LEGACY" else ext
    if preferred:
        return preferred[0]
    return zips[0] if len(zips) == 1 else None


def parse_release(data, kind):
    """GitHub 'latest release' JSON -> info dict, or raise ValueError."""
    asset = pick_asset(data.get("assets", []), kind)
    # The zip's own name (maya_graph_editor-1.1.0.zip) is what gets installed,
    # so it wins over the tag, which may follow a different numbering.
    version = asset_version(asset.get("name", "")) if asset else None
    if version is None:
        version = parse_version(data.get("tag_name", ""))
    if version is None:
        raise ValueError("Release '%s' has no version number in its tag or zip name"
                         % data.get("tag_name"))
    return {
        "version": version,
        "tag": data.get("tag_name", ""),
        "notes_url": data.get("html_url") or RELEASES_PAGE,
        "asset_url": asset.get("browser_download_url") if asset else None,
        "asset_name": asset.get("name") if asset else None,
        "digest": (asset or {}).get("digest") or "",
    }


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

def get_state():
    with _lock:
        return dict(_state)


def _set(**kw):
    with _lock:
        _state.update(kw)


def online_allowed():
    return bool(getattr(bpy.app, "online_access", True))


def _request(url):
    return urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })


# --------------------------------------------------------------------------
# Worker threads (no bpy calls in here)
# --------------------------------------------------------------------------

def fetch_latest(kind):
    """Blocking: returns parse_release(...) of the latest release."""
    try:
        with urllib.request.urlopen(_request(API_LATEST), timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("No release has been published on GitHub yet")
        if e.code in (403, 429):
            raise RuntimeError("GitHub rate limit reached, try again later")
        raise RuntimeError("GitHub answered HTTP %d" % e.code)
    except urllib.error.URLError as e:
        raise RuntimeError("Could not reach GitHub (%s)" % e.reason)
    return parse_release(data, kind)


def _check_worker(installed, kind):
    try:
        info = fetch_latest(kind)
    except Exception as e:
        _set(status="ERROR", message=str(e))
        return
    if info["version"] > installed:
        if not info["asset_url"]:
            _set(status="ERROR", latest=info,
                 message="Release %s has no installable zip attached" % (info["tag"] or "?"))
        else:
            _set(status="AVAILABLE", latest=info,
                 message="Version %s is available" % version_str(info["version"]))
    else:
        _set(status="UP_TO_DATE", latest=info,
             message="You have the latest version (%s)" % version_str(installed))


def _fresh_release(info, kind):
    """The release as GitHub has it *now*: a release can be edited, re-tagged or
    deleted between "Check for Updates" and "Install", which leaves a dead link."""
    if kind is None:
        return info
    try:
        fresh = fetch_latest(kind)
    except Exception:
        return info  # keep the link we have; the download reports any problem
    if fresh.get("asset_url"):
        _set(latest=fresh)
        return fresh
    return info


def _download_worker(info, kind=None):
    try:
        info = _fresh_release(info, kind)
        req = _request(info["asset_url"])
        req.headers["Accept"] = "application/octet-stream"
        folder = tempfile.mkdtemp(prefix="mge_update_")
        path = os.path.join(folder, os.path.basename(info["asset_name"]))
        h = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise RuntimeError("Download is unexpectedly large, aborted")
                h.update(chunk)
                f.write(chunk)
        digest = info.get("digest") or ""
        if digest.startswith("sha256:") and digest[7:].lower() != h.hexdigest():
            raise RuntimeError("Downloaded file failed its checksum, not installed")
        _set(status="DOWNLOADING", message="Installing %s..." % version_str(info.get("version")), zip_path=path)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _set(status="ERROR", message="The release changed on GitHub: click Check for Updates again")
        else:
            _set(status="ERROR", message="Download failed: GitHub answered HTTP %d" % e.code)
    except Exception as e:
        _set(status="ERROR", message="Download failed: %s" % e)


# --------------------------------------------------------------------------
# Main-thread side
# --------------------------------------------------------------------------

def _redraw_prefs():
    wm = bpy.context.window_manager
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type in {'PREFERENCES', 'GRAPH_EDITOR'}:
                area.tag_redraw()


def _poll():
    """Timer: redraw while busy, run the installer once the download is ready."""
    global _timer_running
    st = get_state()
    if st["status"] == "DOWNLOADING" and st["zip_path"]:
        _set(zip_path=None)
        _install(st["zip_path"], st["latest"])
        st = get_state()
    _redraw_prefs()
    if st["status"] in {"CHECKING", "DOWNLOADING"}:
        return 0.25
    _timer_running = False
    return None


def _ensure_timer():
    global _timer_running
    if not _timer_running:
        _timer_running = True
        bpy.app.timers.register(_poll, first_interval=0.25)


def start_check():
    if get_state()["status"] in {"CHECKING", "DOWNLOADING"} or managed_by_blender():
        return
    if not online_allowed():
        _set(status="ERROR", message="Online access is off (Preferences > System > Network)")
        return
    _set(status="CHECKING", message="Checking GitHub...")
    threading.Thread(target=_check_worker, args=(current_version(), install_kind()[0]),
                     daemon=True).start()
    _ensure_timer()


def start_install():
    st = get_state()
    if st["status"] != "AVAILABLE" or not st["latest"]:
        return
    if not online_allowed():
        _set(status="ERROR", message="Online access is off (Preferences > System > Network)")
        return
    _set(status="DOWNLOADING", message="Downloading %s..." % version_str(st["latest"]["version"]), zip_path=None)
    threading.Thread(target=_download_worker, args=(st["latest"], install_kind()[0]),
                     daemon=True).start()
    _ensure_timer()


def _window_override():
    wm = bpy.context.window_manager
    win = wm.windows[0] if wm and wm.windows else None
    return bpy.context.temp_override(window=win) if win else bpy.context.temp_override()


def _install(path, info):
    kind, repo = install_kind()
    tag = version_str(info.get("version")) if info else "?"
    try:
        # Mark success first: an Extension install reloads this very module,
        # so the message is also left in a marker file for the new code.
        message = "Updated to %s. Restart Blender if anything looks stale." % tag
        _set(status="INSTALLED", latest=info, message=message)
        _write_marker(message)
        with _window_override():
            if kind == "EXTENSION":
                bpy.ops.extensions.package_install_files(
                    filepath=path, repo=repo, enable_on_install=True, overwrite=True)
            else:
                bpy.ops.preferences.addon_install(filepath=path, overwrite=True)
                _set(status="INSTALLED", message="Installed %s. Restart Blender to load it." % tag)
    except Exception as e:
        _clear_marker()
        _set(status="ERROR", message="Install failed: %s" % e)
        common.log_exception("updater install")


def _write_marker(message):
    try:
        with open(MARKER, "w", encoding="utf-8") as f:
            json.dump({"message": message, "time": time.time()}, f)
    except OSError:
        pass


def _clear_marker():
    try:
        os.remove(MARKER)
    except OSError:
        pass


def restore_message():
    """Called on register: show the result of an update that just reloaded us."""
    try:
        with open(MARKER, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    _clear_marker()
    if time.time() - data.get("time", 0) < 600:
        _set(status="INSTALLED", message=data.get("message", "Update installed"))


# --------------------------------------------------------------------------
# Operators + UI
# --------------------------------------------------------------------------

class MGE_OT_update_check(bpy.types.Operator):
    bl_idname = "mge.update_check"
    bl_label = "Check for Updates"
    bl_description = "Ask GitHub whether a newer release of this add-on exists"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        start_check()
        return {'FINISHED'}


class MGE_OT_update_install(bpy.types.Operator):
    bl_idname = "mge.update_install"
    bl_label = "Install Update"
    bl_description = "Download the latest release from GitHub and install it over this version"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return get_state()["status"] == "AVAILABLE"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        start_install()
        return {'FINISHED'}


_ICONS = {"ERROR": 'ERROR', "AVAILABLE": 'IMPORT', "UP_TO_DATE": 'CHECKMARK',
          "INSTALLED": 'CHECKMARK', "CHECKING": 'SORTTIME', "DOWNLOADING": 'SORTTIME'}


def draw_prefs(layout, prefs):
    box = layout.box()
    box.label(text="Updates", icon='FILE_REFRESH')
    managed = managed_by_blender()
    if managed:
        box.label(text="Installed version: %s" % version_str(current_version()))
        box.label(text="Updates come through Blender's Extensions (%s)." % managed, icon='INFO')
        return
    st = get_state()
    row = box.row()
    row.label(text="Installed version: %s" % version_str(current_version()))
    busy = st["status"] in {"CHECKING", "DOWNLOADING"}
    sub = row.row()
    sub.enabled = not busy
    sub.operator("mge.update_check", icon='FILE_REFRESH')
    if not online_allowed():
        box.label(text="Online access is off: enable it in Preferences > System > Network.",
                  icon='INFO')
    if st["message"]:
        box.label(text=st["message"], icon=_ICONS.get(st["status"], 'INFO'))
    if st["status"] == "AVAILABLE":
        row = box.row()
        row.scale_y = 1.3
        row.operator("mge.update_install",
                     text="Install %s" % version_str(st["latest"]["version"]), icon='IMPORT')
        row.operator("wm.url_open", text="Release Notes", icon='URL').url = st["latest"]["notes_url"]
    box.operator("wm.url_open", text="All Releases", icon='URL').url = RELEASES_PAGE


def draw_sidebar_notice(layout):
    if managed_by_blender():
        return
    st = get_state()
    if st["status"] == "AVAILABLE":
        layout.label(text="Update %s available" % version_str(st["latest"]["version"]), icon='IMPORT')
        layout.operator("mge.update_install", icon='IMPORT')


classes = (MGE_OT_update_check, MGE_OT_update_install)
