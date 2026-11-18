"""
Penguin Launcher - auto updater.

How it works
  1. You host a small  manifest.json  (see make_manifest.py) plus the launcher's .py files,
     e.g. in a GitHub repo.  Set UPDATE_MANIFEST_URL below to the raw URL of manifest.json.
  2. On startup the launcher downloads the manifest and compares its version with APP_VERSION.
  3. If it is newer, a banner appears. "Update & restart" downloads every listed file,
     checks its SHA-256 and that it is valid Python, backs up the old files to .backup/,
     replaces them, and restarts the launcher.

manifest.json format
  {
    "version": "0.2.0",
    "notes": "What's new...",
    "files": [
      {"name": "penguin_core.py", "url": "https://.../penguin_core.py", "sha256": "..."},
      ...
    ]
  }
"""
import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# >>> CHANGE THIS to the raw URL of your manifest.json, e.g.
#     https://raw.githubusercontent.com/MRtrytytka/penguin-launcher/main/manifest.json
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/MRtrytytka/penguin-launcher/main/manifest.json"

APP_DIR = Path(__file__).resolve().parent
BACKUP_DIR = APP_DIR / ".backup"
USER_AGENT = "penguin-launcher-updater"


def enabled():
    """False until UPDATE_MANIFEST_URL has been set to a real address."""
    return "YOUR_USER" not in UPDATE_MANIFEST_URL


def _version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v)))


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _validate(manifest):
    """Reject anything that could write outside the app folder or fetch from a non-HTTPS URL."""
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise ValueError("Manifest has no files")
    for f in manifest["files"]:
        name = f.get("name", "")
        if Path(name).name != name or not name.endswith(".py") or name.startswith("."):
            raise ValueError(f"Unsafe file name in manifest: {name!r}")
        if not str(f.get("url", "")).startswith("https://"):
            raise ValueError(f"Update URL must be https: {f.get('url')!r}")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(f.get("sha256", ""))):
            raise ValueError(f"Missing/invalid sha256 for {name}")


def check_for_update(current_version):
    """Returns the manifest dict if a newer version exists, else None."""
    if not enabled():
        return None
    manifest = json.loads(_get(UPDATE_MANIFEST_URL))
    if _version_tuple(manifest["version"]) > _version_tuple(current_version):
        _validate(manifest)
        return manifest
    return None


def apply_update(manifest, log=print):
    """Download, verify and install the files listed in the manifest."""
    _validate(manifest)
    files = manifest["files"]
    tmp = Path(tempfile.mkdtemp(prefix="penguin-update-"))
    try:
        for f in files:
            log(f"Downloading {f['name']}")
            data = _get(f["url"], timeout=60)
            if hashlib.sha256(data).hexdigest().lower() != f["sha256"].lower():
                raise RuntimeError(f"Checksum mismatch for {f['name']} - update aborted, nothing was changed")
            staged = tmp / f["name"]
            staged.write_bytes(data)
            try:  # refuse to install files that aren't valid Python
                py_compile.compile(str(staged), cfile=str(tmp / (f["name"] + "c")), doraise=True)
            except py_compile.PyCompileError as e:
                raise RuntimeError(f"{f['name']} is not valid Python - update aborted: {e}")

        shutil.rmtree(BACKUP_DIR, ignore_errors=True)
        BACKUP_DIR.mkdir()
        for f in files:
            current = APP_DIR / f["name"]
            if current.exists():
                shutil.copy2(current, BACKUP_DIR / f["name"])

        for f in files:
            target = APP_DIR / f["name"]
            new = APP_DIR / (f["name"] + ".new")
            shutil.copyfile(tmp / f["name"], new)
            os.replace(new, target)  # atomic replace
        log(f"Updated to {manifest['version']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def rollback(log=print):
    """Restore the files saved by the last update."""
    if not BACKUP_DIR.exists():
        raise RuntimeError("No backup found")
    for f in BACKUP_DIR.glob("*.py"):
        shutil.copy2(f, APP_DIR / f.name)
    log("Restored previous version")


def restart():
    """Start a fresh copy of the launcher (the caller should then quit)."""
    subprocess.Popen([sys.executable] + sys.argv, cwd=os.getcwd(), start_new_session=True)
