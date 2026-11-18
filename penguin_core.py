#!/usr/bin/env python3
"""
Penguin Launcher core (no GUI) - backend for a small Minecraft: Java Edition launcher for Linux with Modrinth support.

Features
  * Vanilla, Fabric and Quilt instances (each instance has its own game folder)
  * Modrinth search + one-click mod install (with required dependencies)
  * Modrinth modpack (.mrpack) install from search results or from a local file
  * Parallel, hash-checked downloads of the game, libraries and assets
  * Automatic Java detection (picks a JVM matching what the game version needs)

Requirements:  python3 (3.8+), python3-tk, and a JDK/JRE (e.g. openjdk-21-jre)
Run:           python3 penguin_launcher.py

Limitations: offline accounts only (no Microsoft login), no Forge/NeoForge.
"""
import glob
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


APP_NAME = "Penguin Launcher"
APP_VERSION = "0.1.0"
# Modrinth asks API clients to send a descriptive, unique User-Agent. Change this to your own.
USER_AGENT = f"penguin-launcher/{APP_VERSION} (personal-project)"

DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "penguin-launcher"
CONFIG_FILE = DATA / "config.json"
INSTANCES = DATA / "instances"
VERSIONS = DATA / "versions"
LIBS = DATA / "libraries"
ASSETS = DATA / "assets"
CACHE = DATA / "cache"

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MODRINTH = "https://api.modrinth.com/v2"
LOADER_META = {
    "fabric": "https://meta.fabricmc.net/v2",
    "quilt": "https://meta.quiltmc.org/v3",
}
LOADERS = ["vanilla", "fabric", "quilt"]

# ============================================================================
#  EDIT HERE  -  Minecraft versions offered in "Add version"
# ============================================================================
# Only these versions can be picked (newest last or first - the order here is the order shown).
# A version is shown only if Mojang's version manifest actually contains it.
ALLOWED_VERSIONS = [
    "1.21.1", "1.21.3", "1.21.4", "1.21.5", "1.21.6", "1.21.7",
    "1.21.8", "1.21.10", "1.21.11",
    "26.1.2", "26.2", "26.3",
]

# ============================================================================
#  EDIT HERE  -  mod groups and profiles shown in "Add version"
# ============================================================================
# A mod is identified by its Modrinth "slug": the last part of its page URL.
#     https://modrinth.com/mod/sodium        ->  "sodium"
#     https://modrinth.com/mod/ferrite-core  ->  "ferrite-core"
# Required dependencies are installed automatically. If a mod has no build for the
# chosen Minecraft version it is skipped (and listed in the console).
#
# 1) Put mods into groups.  To add a mod to Optimized, just add its slug below.
MOD_GROUPS = {
    "base": [
        "fabric-api",
        "in-game-account-switcher",   # switch accounts from inside the game
    ],
    "performance": [
        "sodium",            # rendering engine
        "lithium",           # game logic / server tick
        "ferrite-core",      # lower memory usage
        "modernfix",         # faster loading, less memory
        "immediatelyfast",   # faster HUD / immediate-mode rendering
        "entityculling",     # don't render hidden entities
        "krypton",           # network stack optimization
        "moreculling",       # more face/block culling
        "memoryleakfix",
        "noisium",           # faster world generation
        "scalablelux",       # faster lighting engine
        "iris",
        "sodium-extra",
        "reeses-sodium-options",
        "dynamic-extra",
        "lazydfu",
        "cull-leaves",
        "fastquit",
        "bettergrassify",
        "vmp-fabric",
        "modmenu",
        "entity-model-features",
        "entitytexturefeatures",
        "appleskin",
        "not-enough-animations",
        "jei",
        "3dskinlayers",
        "simple-voice-chat",
        "zoomify",
        "chat-heads",
        "badoptimizations",
        "c2me-fabric",
        "shulkerboxtooltip",
        "modelfix",
        "wavey-capes",
        # "your-mod-slug-here",
    ],
    "performancevcn": [
        "vulkanmod",            # rendering engine
        "not-enough-vulkan",           # game logic / server tick
        "ferrite-core",      # lower memory usage
        "modernfix",         # faster loading, less memory
        "immediatelyfast",   # faster HUD / immediate-mode rendering
        "entityculling",     # don't render hidden entities
        "krypton",           # network stack optimization
        "moreculling",       # more face/block culling
        "memoryleakfix",
        "noisium",           # faster world generation
        "scalablelux",       # faster lighting engine
        "dynamic-extra",
        "lazydfu",
        "cull-leaves",
        "fastquit",
        "bettergrassify",
        "vmp-fabric",
        "modmenu",
        "entity-model-features",
        "entitytexturefeatures",
        "appleskin",
        "not-enough-animations",
        "jei",
        "3dskinlayers",
        "simple-voice-chat",
        "zoomify",
        "chat-heads",
        "badoptimizations",
        "c2me-fabric",
        "shulkerboxtooltip",
        "modelfix",
        "wavey-capes",
        # "your-mod-slug-here",
    ],
}

# 2) Build profiles from groups (+ optional extra "mods").  Add your own profile by
#    copying one of these entries.  loader: "fabric", "quilt" or "vanilla".
PRESETS = {
    "optimized": {
        "title": "⚡  Optimized (Sodium)", "short": "Optimized", "loader": "fabric",
        "desc": "Domyślna instacja dla Penguin Launcher, największy przyrost FPS",
        "groups": ["base", "performance"],
        "mods": [],          # extra single mods for this profile only, e.g. ["modmenu"]
    },
    "optimizedvcn": {
        "title": "⚡  Optimized (Vulcan)", "short": "Vulcan", "loader": "fabric",
        "desc": "Dla zaawansowanych urzytkowników! Jeśli nie wiesz co robisz użyj Optimized (Sodium).",
        "groups": ["base", "performancevcn"],
        "mods": [],          # extra single mods for this profile only, e.g. ["modmenu"]
    },
    "vanilla": {
        "title": "🎮  Vanilla", "short": "Vanilla", "loader": "vanilla",
        "desc": "Zwykły Minecraft. Bez modów", "groups": [], "mods": [],
    },
    "fabric": {
        "title": "🧵  Fabric (empty)", "short": "Fabric", "loader": "fabric",
        "desc": "Sam fabric. Jeśli nie wiesz co zrobić użyj ⚡  Optimized (Sodium).", "groups": ["base"], "mods": [],
    },
}
# ============================================================================


def preset_mods(preset):
    """Flat, de-duplicated list of mod slugs for a profile."""
    out = []
    for g in preset.get("groups", []):
        out += MOD_GROUPS.get(g, [])
    out += preset.get("mods", [])
    removed = set(preset.get("remove_mods", []))
    return [m for m in dict.fromkeys(out) if m not in removed]


# Optional: change profiles WITHOUT editing code, via  ~/.local/share/penguin-launcher/presets.json
#   {
#     "optimized": {"add_mods": ["modmenu", "appleskin"], "remove_mods": ["noisium"]},
#     "my-pack":   {"title": "My pack", "short": "Mine", "loader": "fabric",
#                   "desc": "My favourite mods", "groups": ["base"], "mods": ["sodium", "xaeros-minimap"]}
#   }
PRESETS_FILE = DATA / "presets.json"


def _apply_user_presets():
    try:
        user = json.loads(PRESETS_FILE.read_text())
    except Exception:
        return
    for key, data in user.items():
        if key in PRESETS:
            p = PRESETS[key]
            p["mods"] = list(p.get("mods", [])) + data.get("add_mods", [])
            p["remove_mods"] = data.get("remove_mods", [])
        else:
            PRESETS[key] = {
                "title": data.get("title", key), "short": data.get("short", key),
                "loader": data.get("loader", "fabric"), "desc": data.get("desc", "Custom profile"),
                "groups": data.get("groups", []), "mods": data.get("mods", []),
            }


_apply_user_presets()



# --------------------------------------------------------------------------- networking
def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url):
    return json.loads(http_get(url))


def _hash_file(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest, sha1=None, sha512=None, size=None):
    """Download url to dest. Skips if the file exists with the expected size."""
    dest = Path(dest)
    if dest.exists() and (size is None or dest.stat().st_size == size):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last_err = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 16)
            if sha1 and _hash_file(tmp, "sha1") != sha1:
                raise IOError(f"SHA-1 mismatch for {dest.name}")
            if sha512 and _hash_file(tmp, "sha512") != sha512:
                raise IOError(f"SHA-512 mismatch for {dest.name}")
            os.replace(tmp, dest)
            return
        except Exception as e:  # retry
            last_err = e
    raise RuntimeError(f"Failed to download {url}: {last_err}")


def parallel_download(jobs, log, label, workers=16):
    total = len(jobs)
    if not total:
        return
    done = 0
    step = max(1, total // 20)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(download, **j) for j in jobs]
        for fut in futures:
            fut.result()
            done += 1
            if done % step == 0 or done == total:
                log(f"{label}: {done}/{total}")


def safe_join(base, rel):
    base = Path(base).resolve()
    p = (base / rel).resolve()
    if p != base and not str(p).startswith(str(base) + os.sep):
        raise ValueError(f"Unsafe path in archive: {rel}")
    return p


# --------------------------------------------------------------------------- config / instances
def load_config():
    cfg = {"username": "Player", "memory_mb": 4096, "java_path": ""}
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text()))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    DATA.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def slugify(name):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower() or "instance"


def list_instances():
    out = []
    if INSTANCES.exists():
        for d in sorted(INSTANCES.iterdir()):
            f = d / "instance.json"
            if f.exists():
                try:
                    inst = json.loads(f.read_text())
                    inst["dir"] = str(d)
                    out.append(inst)
                except Exception:
                    pass
    return out


def save_instance(inst):
    d = Path(inst["dir"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "instance.json").write_text(json.dumps({k: v for k, v in inst.items() if k != "dir"}, indent=2))


def create_instance(name, mc, loader, loader_version=None):
    base = slugify(name)
    slug, n = base, 2
    while (INSTANCES / slug).exists():
        slug = f"{base}-{n}"
        n += 1
    inst = {"name": name, "mc": mc, "loader": loader, "loader_version": loader_version,
            "version_id": None, "dir": str(INSTANCES / slug)}
    (Path(inst["dir"]) / "game" / "mods").mkdir(parents=True, exist_ok=True)
    save_instance(inst)
    return inst


def game_dir(inst):
    return Path(inst["dir"]) / "game"


# --------------------------------------------------------------------------- Minecraft install
def list_versions():
    return get_json(MANIFEST_URL)["versions"]


def rule_ok(rules, features=None):
    """Evaluate Mojang-style allow/disallow rules for Linux."""
    if not rules:
        return True
    features = features or {}
    machine = os.uname().machine
    allowed = False
    for r in rules:
        match = True
        o = r.get("os")
        if o:
            if "name" in o and o["name"] != "linux":
                match = False
            arch = o.get("arch")
            if arch == "x86" and machine not in ("i386", "i686"):
                match = False
            if arch == "arm64" and machine not in ("aarch64", "arm64"):
                match = False
        if "features" in r:
            match = match and all(features.get(k, False) == v for k, v in r["features"].items())
        if match:
            allowed = r["action"] == "allow"
    return allowed


def merge_version(parent, child):
    out = dict(parent)
    for k, v in child.items():
        if k == "libraries":
            out[k] = v + parent.get("libraries", [])
        elif k == "arguments":
            out[k] = {kind: parent.get("arguments", {}).get(kind, []) + v.get(kind, [])
                      for kind in ("game", "jvm")}
        elif k != "inheritsFrom":
            out[k] = v
    return out


def load_version_json(vid, log):
    local = VERSIONS / vid / f"{vid}.json"
    if not local.exists():
        manifest = list_versions()
        entry = next((v for v in manifest if v["id"] == vid), None)
        if not entry:
            raise RuntimeError(f"Unknown Minecraft version: {vid}")
        log(f"Downloading version metadata for {vid}")
        download(entry["url"], local, sha1=entry.get("sha1"))
    data = json.loads(local.read_text())
    if "inheritsFrom" in data:
        parent = load_version_json(data["inheritsFrom"], log)
        base = parent["_base"]
        data = merge_version(parent, data)
        data["_base"] = base
    else:
        data["_base"] = data["id"]
    return data


def install_loader(inst, log):
    """Make sure the Fabric/Quilt profile exists locally; returns the version id to launch."""
    mc, loader = inst["mc"], inst["loader"]
    if loader == "vanilla":
        return mc
    if inst.get("version_id") and (VERSIONS / inst["version_id"] / f"{inst['version_id']}.json").exists():
        return inst["version_id"]
    base = LOADER_META[loader]
    lv = inst.get("loader_version")
    if not lv:
        entries = get_json(f"{base}/versions/loader/{urllib.parse.quote(mc)}")
        if not entries:
            raise RuntimeError(f"{loader.title()} does not support Minecraft {mc}")
        pick = next((e for e in entries if e["loader"].get("stable")), entries[0])
        lv = pick["loader"]["version"]
        inst["loader_version"] = lv
    log(f"Installing {loader.title()} loader {lv}")
    raw = http_get(f"{base}/versions/loader/{urllib.parse.quote(mc)}/{urllib.parse.quote(lv)}/profile/json")
    vid = json.loads(raw)["id"]
    p = VERSIONS / vid / f"{vid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)
    return vid


def maven_path(name):
    parts = name.split("@")[0].split(":")
    g, a, v = parts[:3]
    classifier = f"-{parts[3]}" if len(parts) > 3 else ""
    return f"{g.replace('.', '/')}/{a}/{v}/{a}-{v}{classifier}.jar"


def collect_libraries(vdata):
    jobs, classpath, natives = [], [], []

    def add(path, url, sha1=None, size=None):
        jobs.append(dict(url=url, dest=LIBS / path, sha1=sha1, size=size))

    seen_keys = set()  # group:artifact[:classifier] -> keep only the FIRST entry (loader overrides vanilla)
    for lib in vdata.get("libraries", []):
        if not rule_ok(lib.get("rules")):
            continue
        parts = lib.get("name", "").split("@")[0].split(":")
        if len(parts) >= 2:
            key = (parts[0], parts[1], parts[3] if len(parts) > 3 else "")
            if key in seen_keys:
                continue
            seen_keys.add(key)
        dl = lib.get("downloads")
        if dl is None:  # Fabric/Quilt style: Maven coordinates
            path = maven_path(lib["name"])
            url = lib.get("url", "https://libraries.minecraft.net/").rstrip("/") + "/" + path
            add(path, url, lib.get("sha1"), lib.get("size"))
            classpath.append(LIBS / path)
            continue
        art = dl.get("artifact")
        if art and art.get("url"):
            add(art["path"], art["url"], art.get("sha1"), art.get("size"))
            classpath.append(LIBS / art["path"])
        nat = lib.get("natives")
        if nat and "linux" in nat:
            key = nat["linux"].replace("${arch}", "64")
            a = dl.get("classifiers", {}).get(key)
            if a:
                add(a["path"], a["url"], a.get("sha1"), a.get("size"))
                natives.append((LIBS / a["path"], lib.get("extract", {}).get("exclude", [])))
    return jobs, list(dict.fromkeys(classpath)), natives


def install_assets(vdata, gdir, log):
    ai = vdata["assetIndex"]
    idx_path = ASSETS / "indexes" / f"{ai['id']}.json"
    download(ai["url"], idx_path, sha1=ai.get("sha1"), size=ai.get("size"))
    idx = json.loads(idx_path.read_text())
    jobs = []
    for o in idx["objects"].values():
        h = o["hash"]
        jobs.append(dict(url=f"https://resources.download.minecraft.net/{h[:2]}/{h}",
                         dest=ASSETS / "objects" / h[:2] / h, sha1=h, size=o["size"]))
    parallel_download(jobs, log, "Assets")
    target = ASSETS
    if idx.get("virtual") or idx.get("map_to_resources"):
        target = ASSETS / "virtual" / "legacy" if idx.get("virtual") else gdir / "resources"
        for name, o in idx["objects"].items():
            dst = target / name
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ASSETS / "objects" / o["hash"][:2] / o["hash"], dst)
    return target


def prepare(inst, log):
    """Download everything needed to launch. Returns (version_data, classpath, natives_dir, assets_dir)."""
    vid = install_loader(inst, log)
    inst["version_id"] = vid
    save_instance(inst)
    vdata = load_version_json(vid, log)
    base = vdata["_base"]

    client = vdata["downloads"]["client"]
    client_jar = VERSIONS / base / f"{base}.jar"
    log(f"Checking client {base}")
    download(client["url"], client_jar, sha1=client.get("sha1"), size=client.get("size"))

    jobs, classpath, natives = collect_libraries(vdata)
    parallel_download(jobs, log, "Libraries")
    classpath.append(client_jar)

    natives_dir = VERSIONS / vid / "natives"
    if natives_dir.exists():
        shutil.rmtree(natives_dir)
    natives_dir.mkdir(parents=True, exist_ok=True)
    for jar, excludes in natives:
        with zipfile.ZipFile(jar) as z:
            for m in z.namelist():
                if m.endswith("/") or any(m.startswith(e) for e in excludes):
                    continue
                if m.endswith(".so") or ".so." in m:
                    (natives_dir / Path(m).name).write_bytes(z.read(m))

    game_assets = install_assets(vdata, game_dir(inst), log)
    return vdata, classpath, natives_dir, game_assets


# --------------------------------------------------------------------------- Java + launch
def java_major(path):
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=15).stderr
        m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
        major = int(m.group(1))
        return int(m.group(2)) if major == 1 else major
    except Exception:
        return None


def find_java(required, override=""):
    if override:
        return override
    cands = [shutil.which("java")]
    for pat in ("/usr/lib/jvm/*/bin/java", str(Path.home() / ".sdkman/candidates/java/*/bin/java"),
                str(Path.home() / ".jdks/*/bin/java"), "/opt/*/bin/java"):
        cands += glob.glob(pat)
    found = {}
    for c in filter(None, cands):
        major = java_major(c)
        if major and major not in found:
            found[major] = c
    if required in found:
        return found[required]
    higher = sorted(m for m in found if m > required)
    if higher:
        return found[higher[0]]
    raise RuntimeError(f"Java {required}+ not found. Install it (e.g. 'sudo apt install openjdk-{required}-jre') "
                       f"or set the Java path in Settings.")


def offline_uuid(name):
    h = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode()).digest())
    h[6] = (h[6] & 0x0F) | 0x30
    h[8] = (h[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(h)))


def expand_args(args, variables):
    out = []
    for a in args:
        if isinstance(a, dict):
            if not rule_ok(a.get("rules")):
                continue
            v = a["value"]
            vals = [v] if isinstance(v, str) else v
        else:
            vals = [a]
        for v in vals:
            out.append(re.sub(r"\$\{(\w+)\}", lambda m: str(variables.get(m.group(1), m.group(0))), v))
    return out


def build_command(vdata, inst, cfg, java, classpath, natives_dir, assets_dir):
    gdir = game_dir(inst)
    name = cfg["username"] or "Player"
    variables = {
        "auth_player_name": name, "auth_uuid": offline_uuid(name), "auth_access_token": "0",
        "auth_session": "0", "auth_xuid": "0", "clientid": "0", "user_type": "legacy",
        "user_properties": "{}", "version_name": vdata["id"], "version_type": vdata.get("type", "release"),
        "game_directory": str(gdir), "assets_root": str(ASSETS), "game_assets": str(assets_dir),
        "assets_index_name": vdata["assetIndex"]["id"], "natives_directory": str(natives_dir),
        "launcher_name": "penguin-launcher", "launcher_version": APP_VERSION,
        "classpath": ":".join(map(str, classpath)),
    }
    if "arguments" in vdata:
        jvm = expand_args(vdata["arguments"].get("jvm", []), variables)
        game = expand_args(vdata["arguments"].get("game", []), variables)
    else:  # pre-1.13
        jvm = expand_args(["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"], variables)
        game = expand_args(vdata.get("minecraftArguments", "").split(), variables)
    mem = int(cfg["memory_mb"])
    heap = [f"-Xmx{mem}M"] + ([f"-Xms{min(mem, 1024)}M"] if mem >= 1024 else [])
    return [java] + heap + jvm + [vdata["mainClass"]] + game


# --------------------------------------------------------------------------- Modrinth
def mr_search(query, ptype="mod", mc=None, loader=None, limit=30):
    facets = [[f"project_type:{ptype}"]]
    if mc:
        facets.append([f"versions:{mc}"])
    if loader in ("fabric", "quilt") and ptype == "mod":
        facets.append(["categories:fabric", "categories:quilt"] if loader == "quilt" else ["categories:fabric"])
    url = (f"{MODRINTH}/search?query={urllib.parse.quote(query)}&limit={limit}"
           f"&facets={urllib.parse.quote(json.dumps(facets))}")
    return get_json(url)["hits"]


def mr_versions(project_id, mc=None, loaders=None):
    q = []
    if loaders:
        q.append("loaders=" + urllib.parse.quote(json.dumps(loaders)))
    if mc:
        q.append("game_versions=" + urllib.parse.quote(json.dumps([mc])))
    url = f"{MODRINTH}/project/{urllib.parse.quote(project_id)}/version" + ("?" + "&".join(q) if q else "")
    versions = get_json(url)
    return sorted(versions, key=lambda v: v["version_type"] != "release")  # stable sort: releases first


def install_mod(project_id, inst, log, seen=None):
    """Install a Modrinth project (id or slug) plus required deps. Returns True if installed."""
    seen = seen if seen is not None else set()
    if project_id in seen:
        return True
    seen.add(project_id)
    if inst["loader"] == "vanilla":
        raise RuntimeError("Vanilla instances can't use mods. Create a Fabric or Quilt instance.")
    loaders = ["fabric", "quilt"] if inst["loader"] == "quilt" else [inst["loader"]]
    versions = mr_versions(project_id, inst["mc"], loaders)
    if not versions:
        log(f"No compatible version of {project_id} for {inst['mc']} / {inst['loader']}")
        return False
    v = versions[0]
    seen.add(v["project_id"])
    f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
    log(f"Installing {f['filename']}")
    download(f["url"], game_dir(inst) / "mods" / f["filename"], sha512=f["hashes"].get("sha512"), size=f.get("size"))
    for dep in v.get("dependencies", []):
        if dep.get("dependency_type") == "required" and dep.get("project_id"):
            install_mod(dep["project_id"], inst, log, seen)
    return True


def create_from_preset(name, mc, key, log):
    """Create an instance, install the game + loader, then the preset's mods."""
    preset = PRESETS[key]
    inst = create_instance(name, mc, preset["loader"])
    try:
        prepare(inst, log)
    except Exception:
        shutil.rmtree(inst["dir"], ignore_errors=True)
        raise
    mods = preset_mods(preset)
    seen, ok, skipped = set(), [], []
    for slug in mods:
        try:
            (ok if install_mod(slug, inst, log, seen) else skipped).append(slug)
        except Exception as e:
            log(f"Skipped {slug}: {e}")
            skipped.append(slug)
    if mods:
        msg = f"Installed {len(ok)} mod(s)"
        if skipped:
            msg += f"; not available for {mc}: {', '.join(skipped)}"
        log(msg)
    return inst


def install_mrpack(path, name, log):
    with zipfile.ZipFile(path) as z:
        index = json.loads(z.read("modrinth.index.json"))
        deps = index["dependencies"]
        if "forge" in deps or "neoforge" in deps:
            raise RuntimeError("Forge/NeoForge modpacks aren't supported yet (Fabric/Quilt/vanilla only).")
        loader, lv = "vanilla", None
        if "fabric-loader" in deps:
            loader, lv = "fabric", deps["fabric-loader"]
        elif "quilt-loader" in deps:
            loader, lv = "quilt", deps["quilt-loader"]
        inst = create_instance(name or index.get("name", "Modpack"), deps["minecraft"], loader, lv)
        gdir = game_dir(inst)
        jobs = []
        for f in index.get("files", []):
            if f.get("env", {}).get("client") == "unsupported":
                continue
            jobs.append(dict(url=f["downloads"][0], dest=safe_join(gdir, f["path"]),
                             sha1=f["hashes"].get("sha1"), sha512=f["hashes"].get("sha512"), size=f.get("fileSize")))
        parallel_download(jobs, log, "Pack files")
        for member in z.namelist():
            for prefix in ("overrides/", "client-overrides/"):
                if member.startswith(prefix) and not member.endswith("/"):
                    dst = safe_join(gdir, member[len(prefix):])
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(z.read(member))
    return inst


def install_modpack_project(project_id, title, log):
    versions = mr_versions(project_id)
    if not versions:
        raise RuntimeError("This modpack has no downloadable versions.")
    v = versions[0]
    f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
    dest = CACHE / f["filename"]
    log(f"Downloading modpack {title} ({v['version_number']})")
    download(f["url"], dest, sha512=f["hashes"].get("sha512"))
    return install_mrpack(dest, title, log)
