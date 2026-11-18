#!/usr/bin/env python3
"""
Create manifest.json for a new launcher release.

Usage:
  1. Bump APP_VERSION in penguin_core.py (e.g. "0.2.0").
  2. python3 make_manifest.py --version 0.2.0 \
         --base-url https://raw.githubusercontent.com/YOUR_USER/penguin-launcher/main \
         --notes "Added X, fixed Y"
  3. Commit/push the .py files and manifest.json to that repo. Everyone's launcher updates.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_FILES = ["penguin_core.py", "penguin_launcher_qt_new.py", "penguin_updater.py"]

ap = argparse.ArgumentParser()
ap.add_argument("--version", required=True)
ap.add_argument("--base-url", required=True, help="folder URL that serves the files (no trailing slash)")
ap.add_argument("--notes", default="")
ap.add_argument("files", nargs="*", default=DEFAULT_FILES)
args = ap.parse_args()

here = Path(__file__).resolve().parent
core = here / "penguin_core.py"
if core.exists():
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', core.read_text())
    if not m or m.group(1) != args.version:
        sys.exit(f"APP_VERSION in penguin_core.py is {m.group(1) if m else '?'}, but you passed "
                 f"--version {args.version}. Bump it first, or every launch would offer the same update.")

files = []
for name in args.files:
    p = here / name
    if not p.exists():
        sys.exit(f"Missing file: {name}")
    files.append({"name": name, "url": f"{args.base_url}/{name}",
                  "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})

(here / "manifest.json").write_text(json.dumps(
    {"version": args.version, "notes": args.notes, "files": files}, indent=2) + "\n")
print(f"Wrote manifest.json for {args.version} ({len(files)} files)")
