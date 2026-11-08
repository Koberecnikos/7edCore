"""SteamCMD: list game versions (branches), install/update one directory per version."""
import asyncio
import re
import shutil
import time

from aiohttp import web

from . import versions
from .util import (APP_ID, DATA, PANEL_DIR, SERVER_BIN, STEAMCMD, VERSIONS_DIR, load_json, save_json)

BRANCHES_FILE = PANEL_DIR / "branches.json"
KNOWN_FILE = PANEL_DIR / "versions.json"      # branch -> learned version label (from game logs)
BRANCH_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
REFRESH_S = 6 * 3600


def check_branch(name):
    if not name or not BRANCH_RE.match(name):
        raise web.HTTPBadRequest(text=f"Invalid game version / branch: {name!r}")
    return name


def parse_app_info(text):
    """Extract branches from `steamcmd +app_info_print 294420` output."""
    i = text.find('"branches"')
    if i < 0:
        return []
    out = []
    for m in re.finditer(r'"([^"]+)"\s*\{([^{}]*)\}', text[i:i + 80000]):
        d = dict(re.findall(r'"(\w+)"\s+"([^"]*)"', m.group(2)))
        if "buildid" in d:
            out.append({"name": m.group(1), "build": d["buildid"], "updated": int(d.get("timeupdated") or 0),
                        "password": d.get("pwdrequired", "0") == "1", "description": d.get("description", "")})
    return out


class Steam:
    def __init__(self, hub):
        self.hub = hub
        self.lock = asyncio.Lock()
        self.busy = None          # branch being installed
        self.queued = set()
        self.progress = None
        self.cache = load_json(BRANCHES_FILE, {"fetched": 0, "list": []})
        self.known = load_json(KNOWN_FILE, {})

    # ---------------------------------------------------------- paths / state
    def dir(self, branch):
        return VERSIONS_DIR / check_branch(branch)

    def installed(self, branch):
        return (self.dir(branch) / SERVER_BIN).exists()

    def installed_build(self, branch):
        try:
            acf = (self.dir(branch) / "steamapps" / f"appmanifest_{APP_ID}.acf").read_text()
            m = re.search(r'"buildid"\s+"(\d+)"', acf)
            return m.group(1) if m else None
        except OSError:
            return None

    def installed_branches(self):
        if not VERSIONS_DIR.exists():
            return []
        return sorted(d.name for d in VERSIONS_DIR.iterdir() if (d / SERVER_BIN).exists())

    def branch(self, name):
        return next((b for b in self.cache["list"] if b["name"] == name), None)

    def version_of_build(self, build):
        """Named branch (v3.4.0, alpha21.2 ...) that points to the same build -> its version."""
        for b in self.cache["list"]:
            if b["build"] == build and b["name"] != "public":
                v = versions.parse(b["description"]) or versions.parse(b["name"])
                if v:
                    return v
        return None

    def version_label(self, branch):
        """Best known version of the INSTALLED files of a branch."""
        k = self.known.get(branch)
        if k and k.get("build") == self.installed_build(branch):
            return k["label"]
        v = self.version_of_build(self.installed_build(branch)) if self.installed(branch) else None
        if not v:
            b = self.branch(branch)
            v = versions.parse(b["description"]) if b else None
            v = v or versions.parse(branch)
        return v["label"] if v else None

    def learn(self, branch, label):
        """Called when a server log reveals the real version of a branch's files."""
        build = self.installed_build(branch)
        if self.known.get(branch) != {"label": label, "build": build}:
            self.known[branch] = {"label": label, "build": build}
            save_json(KNOWN_FILE, self.known)

    def update_info(self, branch):
        """Update available for an installed branch? + how big it is."""
        cur_build, b = self.installed_build(branch), self.branch(branch)
        if not cur_build or not b:
            return {"available": False}
        if b["build"] == cur_build:
            return {"available": False}
        target = self.version_of_build(b["build"]) or versions.parse(b["description"]) or \
            (versions.parse(branch) if branch != "public" else None)
        cur = versions.parse(self.version_label(branch) or "")
        return {"available": True, "build": b["build"], "target": target["label"] if target else None,
                "current": cur["label"] if cur else None, "kind": versions.update_kind(cur, target)}

    def status(self):
        lst = []
        for b in self.cache["list"]:
            if b["password"]:
                continue
            v = versions.parse(b["description"]) or versions.parse(b["name"])
            if b["name"] == "public":
                v = self.version_of_build(b["build"]) or v
            lst.append({**b, "version": v["label"] if v else None, "installed": self.installed(b["name"]),
                        "installed_build": self.installed_build(b["name"])})
        # installed branches that Steam no longer lists (or list not fetched yet)
        for name in self.installed_branches():
            if not any(x["name"] == name for x in lst):
                lst.append({"name": name, "build": None, "updated": 0, "password": False, "description": "",
                            "version": self.version_label(name), "installed": True,
                            "installed_build": self.installed_build(name)})
        for x in lst:
            if x["installed"]:
                x["version"] = self.version_label(x["name"]) or x["version"]
                x["update"] = self.update_info(x["name"])
                x["used_by"] = [i.name for i in self.hub.instances.values() if i.branch == x["name"]]
        return {"branches": lst, "fetched": self.cache["fetched"], "busy": self.busy, "progress": self.progress,
                "queued": sorted(self.queued)}

    # ---------------------------------------------------------- steamcmd
    async def fetch_branches(self, force=False):
        if not force and time.time() - self.cache.get("fetched", 0) < REFRESH_S and self.cache["list"]:
            return self.cache["list"]
        async with self.lock:
            proc = await asyncio.create_subprocess_exec(
                STEAMCMD, "+login", "anonymous", "+app_info_update", "1", "+app_info_print", APP_ID, "+quit",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            except asyncio.TimeoutError:
                proc.kill()
                raise web.HTTPGatewayTimeout(text="SteamCMD did not answer in time")
            lst = parse_app_info(out.decode("utf-8", "replace"))
            if not lst:
                raise web.HTTPBadGateway(text="Could not read the version list from Steam")
            self.cache = {"fetched": time.time(), "list": lst}
            save_json(BRANCHES_FILE, self.cache)
            return lst

    async def install(self, branch, validate=False, log=print):
        check_branch(branch)
        users = [i.name for i in self.hub.instances.values() if i.branch == branch and i.running()]
        if users:
            raise web.HTTPConflict(text="Stop these servers first: " + ", ".join(users))
        async with self.lock:
            self.busy, self.progress = branch, 0.0
            self.hub.push_all()
            try:
                d = self.dir(branch)
                d.mkdir(parents=True, exist_ok=True)
                args = [STEAMCMD, "+force_install_dir", str(d), "+login", "anonymous", "+app_update", APP_ID]
                if branch != "public":
                    args += ["-beta", branch]
                if validate:
                    args.append("validate")
                args.append("+quit")
                ok = False
                for attempt in (1, 2):     # steamcmd often updates itself on first run and exits
                    log(f"SteamCMD: {'validate ' if validate else ''}{branch} (attempt {attempt})")
                    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                                stderr=asyncio.subprocess.STDOUT)
                    buf, last = b"", 0.0
                    while True:
                        chunk = await proc.stdout.read(4096)
                        if not chunk:
                            break
                        buf += chunk
                        parts = re.split(rb"[\r\n]", buf)
                        buf = parts.pop()
                        for p in parts:
                            line = p.decode("utf-8", "replace").strip()
                            if not line:
                                continue
                            m = re.search(r"progress: ([\d.]+)", line)
                            if m:
                                self.progress = round(float(m.group(1)), 1)
                                if time.monotonic() - last > 2:
                                    last = time.monotonic()
                                    self.hub.push_all()
                            log(line, "steam")
                            if "Success! App" in line and "fully installed" in line:
                                ok = True
                    rc = await proc.wait()
                    if ok:
                        break
                    log(f"SteamCMD exited with code {rc}")
                if not ok:
                    raise web.HTTPInternalServerError(text="Game install/update failed - see console")
                self.known.pop(branch, None)
                save_json(KNOWN_FILE, self.known)
                log(f"Game {branch} installed (build {self.installed_build(branch)})")
                for i in self.hub.instances.values():
                    if i.branch == branch:
                        i.ensure_config()
            finally:
                self.busy, self.progress = None, None
                self.hub.push_all()

    def queue(self, branch, validate=False):
        """Install/update in the background; installs run one after another."""
        check_branch(branch)
        if branch in self.queued:
            return False
        self.queued.add(branch)

        async def run():
            try:
                await self.install(branch, validate=validate, log=lambda l, s="panel": self.hub.broadcast(l, s))
            except web.HTTPException as e:
                self.hub.broadcast(f"SteamCMD {branch}: {e.text}")
            except Exception as e:
                self.hub.broadcast(f"SteamCMD {branch}: error {e!r}")
            finally:
                self.queued.discard(branch)
        asyncio.create_task(run())
        return True

    def remove(self, branch):
        check_branch(branch)
        users = [i.name for i in self.hub.instances.values() if i.branch == branch]
        if users:
            raise web.HTTPConflict(text="This version is used by: " + ", ".join(users))
        d = self.dir(branch)
        if d.exists():
            shutil.rmtree(d)

    def migrate_legacy(self):
        """v1/v2 layout had a single install in /data/server -> /data/versions/public."""
        old = DATA / "server"
        if (old / SERVER_BIN).exists() and not (VERSIONS_DIR / "public").exists():
            VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
            old.rename(VERSIONS_DIR / "public")
            print("[7edcore] migrated /data/server -> /data/versions/public", flush=True)
