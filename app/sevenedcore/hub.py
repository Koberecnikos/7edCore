"""All servers + shared game installs + background loops (stats, scheduler, updates)."""
import asyncio
import json
import os
import shutil
import time

import psutil
from aiohttp import web

from . import __version__
from .instance import CompatError, Instance
from .mods import _get_json
from .steam import Steam
from .util import (DATA, GAME_PORT_BASE, INST_ROOT, MAX_SERVERS, PANEL_DIR, TELNET_PORT_BASE, TRASH, WEB_PORT_BASE,
                   get_prop, load_json, save_json, slugify, stamp, write_config_props)

REGISTRY_FILE = PANEL_DIR / "instances.json"
GLOBAL_FILE = PANEL_DIR / "global.json"
DEFAULT_GLOBAL = {"github_token": "", "nexus_key": ""}
PANEL_REPO = os.environ.get("SEVENEDCORE_REPO", "").strip()     # owner/repo for "new 7edCore version" notice


class Hub:
    def __init__(self):
        self.glob = {**DEFAULT_GLOBAL, **load_json(GLOBAL_FILE, {})}
        self.instances, self.order = {}, []
        self.steam = Steam(self)
        self.panel_update = None

    # ---------------------------------------------------------- registry / migrations
    def load(self):
        self.steam.migrate_legacy()
        self._migrate_single()
        reg = load_json(REGISTRY_FILE, {"order": [], "names": {}})
        for iid in reg["order"]:
            if (INST_ROOT / iid).is_dir():
                self.instances[iid] = Instance(self, iid, reg["names"].get(iid, iid))
                self.order.append(iid)
        if not self.order:
            self.create("Server 1", announce=False)

    def save_registry(self):
        save_json(REGISTRY_FILE, {"order": self.order, "names": {i: self.instances[i].name for i in self.order}})

    def _migrate_single(self):
        """Old single-server layout (/data/config, /data/userdata ...) -> /data/instances/server-1."""
        old_cfg = DATA / "config" / "serverconfig.xml"
        if not old_cfg.exists() or REGISTRY_FILE.exists():
            return
        dst = INST_ROOT / "server-1"
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("config", "userdata", "logs", "backups"):
            if (DATA / name).exists() and not (dst / name).exists():
                shutil.move(str(DATA / name), str(dst / name))
        for f in ("settings.json", "state.json"):
            if (PANEL_DIR / f).exists():
                shutil.move(str(PANEL_DIR / f), str(dst / f))
        cfg = dst / "config" / "serverconfig.xml"
        if cfg.exists():
            write_config_props(cfg, {"TelnetPort": str(TELNET_PORT_BASE), "UserDataFolder": str(dst / "userdata")})
        save_json(REGISTRY_FILE, {"order": ["server-1"], "names": {"server-1": "Server 1"}})
        print("[7edcore] migrated single-server data -> instances/server-1", flush=True)

    def free_slot(self):
        used = set()
        for i in self.instances.values():
            try:
                used.add((int(get_prop(i.cfg, "ServerPort") or 0) - GAME_PORT_BASE) // 10)
            except ValueError:
                pass
        return next((k for k in range(MAX_SERVERS) if k not in used), None)

    def create(self, name, clone_from=None, branch=None, announce=True):
        name = (name or "").strip()[:40]
        if not name:
            raise web.HTTPBadRequest(text="Enter a server name")
        if len(self.instances) >= MAX_SERVERS:
            raise web.HTTPConflict(text=f"Maximum is {MAX_SERVERS} servers")
        base, n = slugify(name), 2
        iid = base
        while iid in self.instances or (INST_ROOT / iid).exists():
            iid, n = f"{base}-{n}", n + 1
        k = self.free_slot()
        inst = Instance(self, iid, name)
        if clone_from and clone_from in self.instances:
            src = self.instances[clone_from]
            if src.cfg.exists():
                shutil.copy2(src.cfg, inst.cfg)
            inst.settings = json.loads(json.dumps(src.settings))
        if branch:
            inst.settings["game_version"] = branch
        inst.save_settings()
        assign = {"ServerPort": str(GAME_PORT_BASE + 10 * k), "TelnetPort": str(TELNET_PORT_BASE + k),
                  "WebDashboardPort": str(WEB_PORT_BASE + k), "ServerName": name}
        if not clone_from:
            assign["GameName"] = slugify(name).replace("-", "_") or "Game"
        inst.save_pstate(assign=assign)
        if inst.cfg.exists():
            inst.ensure_config(assign)
        else:
            inst.ensure_config()
        self.instances[iid] = inst
        self.order.append(iid)
        self.save_registry()
        if announce:
            inst.note(f"Server created: {name} (port {assign['ServerPort']})")
        return inst

    async def delete(self, iid):
        inst = self.get(iid)
        if inst.running():
            raise web.HTTPConflict(text="Stop the server first")
        if len(self.instances) == 1:
            raise web.HTTPConflict(text="The last server cannot be deleted")
        self.order.remove(iid)
        del self.instances[iid]
        self.save_registry()
        TRASH.mkdir(exist_ok=True)
        shutil.move(str(inst.dir), str(TRASH / f"{iid}_{stamp()}"))
        for q in list(inst.subscribers):
            q.put_nowait(json.dumps({"type": "deleted"}))

    def get(self, iid) -> Instance:
        inst = self.instances.get(iid)
        if not inst:
            raise web.HTTPNotFound(text="Server not found")
        return inst

    @staticmethod
    def _ports(inst):
        ps = set()
        try:
            g = int(get_prop(inst.cfg, "ServerPort") or 0)
            ps.update(range(g, g + 4))
        except ValueError:
            pass
        ps.add(get_prop(inst.cfg, "TelnetPort"))
        if get_prop(inst.cfg, "WebDashboardEnabled") == "true":
            ps.add(get_prop(inst.cfg, "WebDashboardPort"))
        return {str(p) for p in ps if p}

    def port_conflict(self, me):
        mine = self._ports(me)
        for o in self.instances.values():
            if o is not me and o.running():
                both = mine & self._ports(o)
                if both:
                    return f"Port {', '.join(sorted(both))} is used by server {o.name} - change the ports in settings"
        return None

    def builtin_worlds(self, branch):
        d = self.steam.dir(branch) / "Data" / "Worlds"
        return sorted(x.name for x in d.iterdir() if x.is_dir() and x.name not in ("Empty", "Playtesting")) if d.exists() else []

    def push_all(self):
        for i in self.instances.values():
            i.push_state()

    def broadcast(self, line, src="panel"):
        for i in self.instances.values():
            i.console(src, line)

    def overview(self):
        return {"instances": [{"id": i.id, "name": i.name, "state": i.state, "players": len(i.players),
                               "port": get_prop(i.cfg, "ServerPort"), "world": get_prop(i.cfg, "GameWorld"),
                               "version": i.game_version_label(), "branch": i.branch,
                               "notices": bool(i.notices)} for i in (self.instances[x] for x in self.order)],
                "max": MAX_SERVERS, "panel": {"version": __version__, "update": self.panel_update, "repo": PANEL_REPO},
                "steam_busy": self.steam.busy, "steam_progress": self.steam.progress}

    # ---------------------------------------------------------- game updates
    async def update_game(self, branch, reason=""):
        """Stop servers on this game version, back them up, update, start those that ran."""
        users = [i for i in self.instances.values() if i.branch == branch]
        running = [i for i in users if i.running()]
        for i in running:
            await i.say("Server is restarting for a game update, saving the world...", "FF4444")
        await asyncio.sleep(3 if running else 0)
        for i in running:
            await i.stop(user=False, reason=f"game update {reason}".strip())
        for i in users:
            if (i.userdata / "Saves").exists():
                try:
                    await i.create_backup("pre-update")
                except web.HTTPException as e:
                    i.note(f"Pre-update backup failed: {e.text}")
        await self.steam.install(branch, log=lambda line, src="panel": self.broadcast(line, src))
        for i in users:
            i.notices.pop("game_update", None)
        for i in running:
            try:
                await i.start(reason="after game update")
            except CompatError as e:
                i.note(f"Not started after the update: {e.message} ({e.compat.get('save_version')} -> {e.compat.get('game')})")

    @staticmethod
    def _game_policy_allows(policy, kind):
        return (policy == "patch" and kind == "patch") or (policy == "minor" and kind in ("patch", "minor"))

    async def apply_pending(self, inst):
        """Apply allowed pending updates for a stopped server (scheduled restart window)."""
        info = self.steam.update_info(inst.branch)
        users = [i for i in self.instances.values() if i.branch == inst.branch]
        if info.get("available") and all(self._game_policy_allows(i.settings["game_updates"], info["kind"]) for i in users) \
                and all(i is inst or not i.running() for i in users):
            await self.update_game(inst.branch, reason=f"auto ({info['kind']})")
        await self._apply_mod_updates(inst, stopped_already=True)

    async def check_updates(self, force_branches=False):
        try:
            await self.steam.fetch_branches(force=force_branches)
        except web.HTTPException as e:
            print(f"[7edcore] branch refresh failed: {e.text}", flush=True)
            return
        branches = {i.branch for i in self.instances.values() if self.steam.installed(i.branch)}
        for b in branches:
            info = self.steam.update_info(b)
            users = [i for i in self.instances.values() if i.branch == b]
            for i in users:
                if info.get("available") and i.settings["game_updates"] != "off":
                    if i.notices.get("game_update", {}).get("build") != info["build"]:
                        i.note(f"Game update available: {info.get('current') or '?'} -> {info.get('target') or 'build ' + info['build']} ({info['kind']})")
                    i.notices["game_update"] = info
                else:
                    i.notices.pop("game_update", None)
            if not info.get("available"):
                continue
            auto = all(self._game_policy_allows(i.settings["game_updates"], info["kind"]) for i in users)
            window = all(i.settings["update_window"] != "restart" and i.update_window_ok() for i in users)
            if auto and window:
                await self.update_game(b, reason=f"auto ({info['kind']})")
        self.push_all()

    # ---------------------------------------------------------- mod updates
    async def check_mods(self, inst):
        tok, nk = self.glob.get("github_token"), self.glob.get("nexus_key")
        found = []
        for m in inst.mods.list():
            if not m.get("source"):
                continue
            res = await inst.mods.check(m["folder"], tok, nk)
            if res.get("update"):
                found.append({"folder": m["folder"], "name": m["name"], "latest": res.get("latest"),
                              "compat": res.get("compat"), "manual": res.get("manual", False)})
        if found and inst.settings["mod_updates"] != "off":
            inst.notices["mods"] = found
        else:
            inst.notices.pop("mods", None)
        return found

    async def _apply_mod_updates(self, inst, stopped_already=False):
        if inst.settings["mod_updates"] != "auto":
            return
        todo = [m for m in inst.notices.get("mods", []) if m["compat"] == "yes" and not m["manual"]]
        if not todo:
            return
        was = inst.running() and not stopped_already
        if was:
            await inst.say("Server restarts for mod updates, saving the world...", "FF4444")
            await asyncio.sleep(3)
            await inst.stop(user=False, reason="mod updates")
        if (inst.userdata / "Saves").exists():
            await inst.create_backup("pre-update")
        for m in todo:
            try:
                rep = await inst.mods.update(m["folder"], self.glob.get("github_token"))
                inst.note(f"Mod updated: {m['name']} -> {m['latest']}" + "".join(
                    f" (kept your {len(r['kept'])} edited files, {len(r['conflicts'])} need review)" for r in rep if r["kept"]))
            except web.HTTPException as e:
                inst.note(f"Mod update failed: {m['name']}: {e.text}")
        await self.check_mods(inst)
        if was:
            await inst.start(reason="after mod updates")

    # ---------------------------------------------------------- loops
    async def stats_loop(self):
        psutil.cpu_percent(None)
        tick = 0
        while True:
            await asyncio.sleep(5)
            tick += 1
            vm, sw = psutil.virtual_memory(), psutil.swap_memory()
            host = {"t": time.time(), "host_cpu": psutil.cpu_percent(None), "host_mem": vm.used,
                    "host_mem_total": vm.total, "swap_used": sw.used, "swap_total": sw.total,
                    "load": os.getloadavg(), "cpu_temp": None}
            try:
                pk = [t.current for t in psutil.sensors_temperatures().get("coretemp", []) if "Package" in (t.label or "")]
                host["cpu_temp"] = pk[0] if pk else None
            except Exception:
                pass
            try:
                du = shutil.disk_usage(DATA)
                host["disk_used"], host["disk_total"] = du.used, du.total
            except OSError:
                pass
            for inst in list(self.instances.values()):
                try:
                    await inst.collect_stats(host, tick)
                except Exception as e:
                    print(f"[7edcore] stats {inst.id}: {e!r}", flush=True)

    async def scheduler_loop(self):
        while True:
            await asyncio.sleep(15)
            for inst in list(self.instances.values()):
                await inst.schedule_tick()

    async def updates_loop(self):
        await asyncio.sleep(60)
        n = 0
        while True:
            try:
                await self.check_updates()
                if n % 12 == 0:                        # mods + panel: every 6 h
                    for inst in list(self.instances.values()):
                        if inst.settings["mod_updates"] != "off":
                            await self.check_mods(inst)
                            if inst.settings["update_window"] != "restart" and inst.update_window_ok():
                                await self._apply_mod_updates(inst)
                    await self.check_panel_update()
            except Exception as e:
                print(f"[7edcore] update loop: {e!r}", flush=True)
            n += 1
            await asyncio.sleep(1800)

    async def check_panel_update(self):
        if not PANEL_REPO:
            return
        try:
            r = await _get_json(f"https://api.github.com/repos/{PANEL_REPO}/releases/latest")
            tag = (r.get("tag_name") or "").lstrip("v")
            if tag and tuple(int(x) for x in tag.split(".")[:3] if x.isdigit()) > \
                    tuple(int(x) for x in __version__.split(".")[:3]):
                self.panel_update = {"version": tag, "url": r.get("html_url")}
            else:
                self.panel_update = None
        except Exception:
            pass
