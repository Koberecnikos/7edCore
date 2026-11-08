"""One 7 Days to Die server (instance): process, console, stats, backups, schedule, worlds."""
import asyncio
import collections
import datetime as dt
import json
import os
import re
import secrets
import shutil
import signal
import tempfile
import time
from pathlib import Path

import psutil
from aiohttp import web

from . import versions
from .mods import Mods
from .util import (INST_ROOT, LOGLINE, NCPU, SERVER_BIN, cpu_list, get_prop, load_json, now_ts,
                   parse_hhmm, read_config_props, rel, safe_extract, save_json, stamp, write_config_props)

DEFAULT_SETTINGS = {
    "game_version": "public",       # Steam branch this server runs (public, v3.4.0, alpha21.2 ...)
    "autostart": "last",            # off | always | last (start again if it was running before)
    "crash_restart": True,          # restart after a crash (max 3x in 15 min)
    "backup_interval_hours": 6,     # 0 = off
    "backup_keep": 10,
    "backup_include_worlds": True,  # include GeneratedWorlds (maps, hundreds of MB)
    "backup_only_when_running": True,
    "schedule": [],                 # [{"id","enabled","days":[1..7],"time":"HH:MM","action","warn":[min],"message"}]
    "shutdown_timeout": 150,
    "server_cpus": "auto",          # auto = all cores except the last one (reserved for backups)
    "backup_cpus": "auto",          # auto = last core
    "ram_limit_gb": 0,              # 0 = off
    "ram_action": "warn",           # warn | restart (graceful, with in-game warning)
    "game_updates": "notify",       # off | notify | patch | minor   (major updates are never automatic)
    "mod_updates": "notify",        # off | notify | auto            (auto = only releases made for this game version)
    "update_window": "empty",       # empty (nobody online) | stopped (only while stopped) | restart (at scheduled restart)
    "preset": "",                   # last applied difficulty preset (informational)
}
ACTIONS = ("start", "stop", "restart", "update_restart", "backup")


class CompatError(Exception):
    def __init__(self, message, compat):
        super().__init__(message)
        self.message, self.compat = message, compat


class Instance:
    def __init__(self, hub, iid, name):
        self.hub, self.id, self.name = hub, iid, name
        self.dir = INST_ROOT / iid
        self.cfg = self.dir / "config" / "serverconfig.xml"
        self.userdata = self.dir / "userdata"
        self.backups = self.dir / "backups"
        self.logs = self.dir / "logs"
        self.settings_file = self.dir / "settings.json"
        self.state_file = self.dir / "state.json"
        for d in (self.dir / "config", self.userdata, self.backups, self.logs):
            d.mkdir(parents=True, exist_ok=True)
        raw = load_json(self.settings_file, {})
        if raw.get("restart_enabled"):        # panel v2 daily restart -> schedule rule
            raw.setdefault("schedule", []).append({
                "id": secrets.token_hex(4), "enabled": True, "days": [1, 2, 3, 4, 5, 6, 7],
                "time": raw.get("restart_time", "05:00"),
                "action": "update_restart" if raw.get("restart_update") else "restart",
                "warn": raw.get("restart_warn_minutes", [10, 5, 1]), "message": ""})
        for k in ("restart_enabled", "restart_time", "restart_warn_minutes", "restart_update", "steam_branch",
                  "update_on_start"):
            raw.pop(k, None)
        self.settings = {**DEFAULT_SETTINGS, **raw}
        self.pstate = load_json(self.state_file, {})
        self.mods = Mods(self)
        self.state, self.busy = "stopped", ""
        self.proc, self.started_at, self.logfile = None, None, None
        self.console_buf = collections.deque(maxlen=4000)
        self.history = collections.deque(maxlen=720)
        self.subscribers = set()
        self.tr = self.tw = None
        self.cmd_lock, self.backup_lock, self.op_lock = asyncio.Lock(), asyncio.Lock(), asyncio.Lock()
        self.cmd_buf, self.cmd_last = None, 0.0
        self.players, self.gametime, self.meminfo, self.last_stats = [], "", {}, {}
        self.crash_times, self.tasks = [], []
        self.warned = set()
        self.ready_noted = False
        self.run_version = None
        self.procs_cache = {}
        self.ram_over = 0
        self.ram_action_at = 0
        self.notices = {}

    # ---------------------------------------------------------- basics
    @property
    def branch(self):
        return self.settings.get("game_version") or "public"

    @property
    def server_dir(self):
        return self.hub.steam.dir(self.branch)

    def game_version_label(self):
        return self.run_version or self.hub.steam.version_label(self.branch)

    def publish(self, msg):
        data = json.dumps(msg, ensure_ascii=False)
        for q in list(self.subscribers):
            if q.qsize() < 2000:
                q.put_nowait(data)

    def console(self, src, line):
        item = {"t": now_ts(), "src": src, "line": line}
        self.console_buf.append(item)
        self.publish({"type": "log", **item})

    def note(self, text, src="panel"):
        self.console(src, text)

    def push_state(self):
        self.publish({"type": "state", **self.status()})

    def set_state(self, st):
        if st != self.state:
            self.state = st
            self.push_state()

    def set_busy(self, text):
        self.busy = text
        self.push_state()

    def save_pstate(self, **kw):
        self.pstate.update(kw)
        save_json(self.state_file, self.pstate)

    def save_settings(self):
        save_json(self.settings_file, self.settings)

    def running(self):
        return self.proc is not None and self.proc.returncode is None

    def ports(self):
        return {"game": get_prop(self.cfg, "ServerPort"), "telnet": get_prop(self.cfg, "TelnetPort"),
                "web": get_prop(self.cfg, "WebDashboardPort"),
                "web_enabled": get_prop(self.cfg, "WebDashboardEnabled") == "true"}

    def status(self):
        st = self.hub.steam
        return {
            "id": self.id, "name": self.name, "state": self.state, "busy": self.busy,
            "console_connected": self.tw is not None, "started_at": self.started_at,
            "players": self.players, "gametime": self.gametime, "meminfo": self.meminfo,
            "world": {k: get_prop(self.cfg, k) for k in ("GameWorld", "GameName", "WorldGenSeed", "WorldGenSize",
                                                          "ServerName", "ServerPort", "ServerMaxPlayerCount")},
            "ports": self.ports(), "last_backup": self.pstate.get("last_backup"),
            "game": {"branch": self.branch, "installed": st.installed(self.branch), "version": self.game_version_label(),
                     "build": st.installed_build(self.branch), "busy": st.busy, "progress": st.progress},
            "compat": self.compat_check(), "notices": self.notices,
            "ram_limit_gb": self.settings.get("ram_limit_gb"),
        }

    # ---------------------------------------------------------- config
    def ensure_config(self, assign=None):
        """Copy the default serverconfig.xml from the game install + enforce per-server values."""
        forced = {"UserDataFolder": str(self.userdata), "TelnetEnabled": "true"}
        if not self.cfg.exists():
            src = self.server_dir / "serverconfig.xml"
            if not src.exists():
                return False
            shutil.copy2(src, self.cfg)
            forced.update(self.pstate.get("assign") or {})
        cur = {n: v for n, v, _ in read_config_props(self.cfg)}
        if assign:
            forced.update(assign)
        if not cur.get("TelnetPort"):
            forced.setdefault("TelnetPort", "8081")
        changes = {k: v for k, v in forced.items() if cur.get(k) != v}
        if changes:
            write_config_props(self.cfg, changes)
        return True

    # ---------------------------------------------------------- saves & version compatibility
    def active_save(self):
        """'World/Game' of the save the current config will load, if it exists."""
        game = get_prop(self.cfg, "GameName")
        saves = self.userdata / "Saves"
        if not game or not saves.exists():
            return None
        world = get_prop(self.cfg, "GameWorld")
        if world and world != "RWG" and (saves / world / game).is_dir():
            return f"{world}/{game}"
        cands = [d for d in saves.glob(f"*/{game}") if d.is_dir()]
        if not cands:
            return None
        return f"{max(cands, key=lambda d: d.stat().st_mtime).parent.name}/{game}"

    def save_meta(self, key):
        return (self.pstate.get("saves_meta") or {}).get(key)

    def compat_check(self, target_label=None):
        game_label = target_label or self.game_version_label()
        key = self.active_save()
        if not key:
            return {"level": "new", "game": game_label}
        meta = self.save_meta(key)
        if not meta or not meta.get("last"):
            return {"level": "unknown", "save": key, "game": game_label}
        c = versions.compat(versions.parse(meta["last"]), versions.parse(game_label or ""))
        c.update(save=key, save_version=meta["last"], created=meta.get("created"), game=game_label)
        return c

    def _track_save_version(self):
        if not self.run_version:
            return
        key = self.active_save()
        if not key:
            return
        meta = dict(self.save_meta(key) or {})
        if meta.get("last") == self.run_version:
            return
        meta.setdefault("created", self.run_version)
        meta["last"] = self.run_version
        sm = dict(self.pstate.get("saves_meta") or {})
        sm[key] = meta
        self.save_pstate(saves_meta=sm)

    # ---------------------------------------------------------- process
    async def start(self, force=False, reason=""):
        async with self.op_lock:
            if self.running():
                raise web.HTTPConflict(text="Server is already running")
            if not self.hub.steam.installed(self.branch):
                raise web.HTTPConflict(text=f"Game version '{self.branch}' is not installed yet")
            if self.hub.steam.busy == self.branch:
                raise web.HTTPConflict(text="This game version is being installed / updated")
            c = self.compat_check()
            if c["level"] in ("major", "downgrade") and not force:
                raise CompatError("The save was made with a different game version", c)
            if not self.ensure_config():
                raise web.HTTPConflict(text="serverconfig.xml is missing")
            conflict = self.hub.port_conflict(self)
            if conflict:
                raise web.HTTPConflict(text=conflict)
            sdir = self.server_dir
            self.logfile = self.logs / f"server_{stamp()}.log"
            self.logfile.touch()
            env = dict(os.environ, LD_LIBRARY_PATH=str(sdir))
            args = [str(sdir / SERVER_BIN), "-logfile", str(self.logfile), "-quit", "-batchmode",
                    "-nographics", f"-configfile={self.cfg}", "-dedicated"]
            cpus = cpu_list(self.settings["server_cpus"], f"0-{NCPU - 2}" if NCPU > 2 else "")
            if cpus and shutil.which("taskset"):
                args = ["taskset", "-c", cpus] + args
            self.note(f"Starting server{(' (' + reason + ')') if reason else ''}: game {self.branch} "
                      f"({self.game_version_label() or '?'}), cores {cpus or 'all'}, log {self.logfile.name}")
            self.proc = await asyncio.create_subprocess_exec(
                *args, cwd=str(sdir), env=env, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, start_new_session=True)
            self.started_at = now_ts()
            self.ready_noted = False
            self.run_version = None
            self.players, self.gametime, self.meminfo = [], "", {}
            self.ram_over = 0
            self.set_state("starting")
            self.save_pstate(was_running=True)
            proc = self.proc
            self.tasks = [asyncio.create_task(self._read_stdout(proc)),
                          asyncio.create_task(self._tail_log(proc, self.logfile)),
                          asyncio.create_task(self._telnet_loop(proc)),
                          asyncio.create_task(self._wait_exit(proc))]

    async def _read_stdout(self, proc):
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self.console("stdout", line)

    async def _tail_log(self, proc, path):
        pos, buf = 0, ""
        while proc.returncode is None:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
            except OSError:
                chunk = ""
            if chunk:
                buf += chunk
                *lines, buf = buf.split("\n")
                for line in lines:
                    line = line.rstrip("\r")
                    if line:
                        self.console("log", line)
                        self._watch(line)
            await asyncio.sleep(0.3)

    def _watch(self, line):
        if self.run_version is None and "Compatibility Version:" in line:
            m = re.search(r"Compatibility Version:\s*([^,]+)", line)
            v = versions.parse(m.group(1)) if m else None
            if v:
                self.run_version = v["label"]
                self.hub.steam.learn(self.branch, v["label"])
                self.note(f"Game version: {v['label']}")
        if not self.ready_noted and ("GameServer.LogOn successful" in line or "StartGame done" in line):
            self.ready_noted = True
            self.note("Server is ready for players")
            self._track_save_version()

    async def _telnet_loop(self, proc):
        while proc.returncode is None:
            port = int(get_prop(self.cfg, "TelnetPort", "8081") or 8081)
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 3)
            except (OSError, asyncio.TimeoutError):
                await asyncio.sleep(3)
                continue
            self.tr, self.tw = r, w
            self.note(f"Console connected (telnet {port})")
            if self.state == "starting":
                self.set_state("running")
            self.push_state()
            try:
                while True:
                    raw = await r.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if "enter password" in line.lower():
                        w.write((get_prop(self.cfg, "TelnetPassword") + "\r\n").encode())
                        await w.drain()
                        continue
                    if self.cmd_buf is not None and line.strip() and not LOGLINE.match(line):
                        self.cmd_buf.append(line)
                        self.cmd_last = time.monotonic()
            except (OSError, asyncio.IncompleteReadError):
                pass
            finally:
                self.tr = self.tw = None
                self.push_state()
            await asyncio.sleep(2)

    async def command(self, cmd, timeout=5.0, idle=0.7, quiet=False):
        if not self.tw:
            raise web.HTTPConflict(text="Console not connected (server stopped or still starting)")
        async with self.cmd_lock:
            self.cmd_buf, self.cmd_last = [], time.monotonic()
            try:
                self.tw.write((cmd + "\r\n").encode())
                await self.tw.drain()
            except OSError as e:
                self.cmd_buf = None
                raise web.HTTPConflict(text=f"Console: {e}")
            t0 = time.monotonic()
            while time.monotonic() - t0 < timeout:
                await asyncio.sleep(0.1)
                if self.cmd_buf and time.monotonic() - self.cmd_last > idle:
                    break
            out, self.cmd_buf = self.cmd_buf or [], None
        if not quiet:
            self.console("cmd", f"> {cmd}")
            for line in out:
                self.console("cmd", line)
        return out

    async def say(self, text, color="FFAA00"):
        if self.tw:
            try:
                await self.command(f'say "[{color}]{text.replace(chr(34), chr(39))}[-]"', quiet=True)
            except web.HTTPException:
                pass

    async def _wait_exit(self, proc):
        rc = await proc.wait()
        self._track_save_version()
        for t in self.tasks:
            if t is not asyncio.current_task():
                t.cancel()
        self.tr = self.tw = None
        self.players = []
        expected = self.state == "stopping"
        self.note(f"Server exited (code {rc}){'' if expected else ' - UNEXPECTED'}")
        self.proc, self.started_at = None, None
        if expected:
            self.set_state("stopped")
            return
        self.set_state("crashed")
        if self.settings["crash_restart"]:
            t = now_ts()
            self.crash_times = [x for x in self.crash_times if t - x < 900] + [t]
            if len(self.crash_times) <= 3:
                self.note(f"Restarting after crash ({len(self.crash_times)}/3) in 10 s")
                await asyncio.sleep(10)
                if self.state == "crashed":
                    try:
                        await self.start(force=True, reason="crash restart")
                    except (web.HTTPException, CompatError) as e:
                        self.note(f"Restart failed: {getattr(e, 'text', e)}")
            else:
                self.note("Crashed 3 times in 15 minutes - automatic restart disabled, check the log")

    def _signal(self, proc, sig):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass

    async def stop(self, user=True, reason=""):
        async with self.op_lock:
            proc = self.proc
            if not proc or proc.returncode is not None:
                self.set_state("stopped")
                if user:
                    self.save_pstate(was_running=False)
                return
            self.set_state("stopping")
            if user:
                self.save_pstate(was_running=False)
            self.note(f"Stopping server{(' - ' + reason) if reason else ''}: saving the world...")
            for _ in range(40):
                if self.tw or proc.returncode is not None:
                    break
                await asyncio.sleep(0.5)
            timeout = self.settings["shutdown_timeout"]
            if self.tw:
                try:
                    await self.command("saveworld", timeout=20, idle=2)
                    await asyncio.sleep(2)
                    await self.command("shutdown", timeout=3)
                except web.HTTPException:
                    pass
            elif proc.returncode is None:
                self.note("Console not connected (still starting) - sending SIGTERM")
                self._signal(proc, signal.SIGTERM)
                timeout = 60
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                self.note("Server does not respond - SIGTERM")
                self._signal(proc, signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=30)
                except asyncio.TimeoutError:
                    self.note("Still running - SIGKILL")
                    self._signal(proc, signal.SIGKILL)
                    await proc.wait()
            await asyncio.sleep(0.5)
            self.set_state("stopped")

    async def kill(self):
        if self.running():
            self.set_state("stopping")
            self.save_pstate(was_running=False)
            self.note("KILL (no save)")
            self._signal(self.proc, signal.SIGKILL)

    async def restart(self, reason="", update=False):
        await self.stop(user=False, reason=reason or "restart")
        if update:
            await self.hub.update_game(self.branch, reason=reason or "update")
        elif reason == "schedule":
            await self.hub.apply_pending(self)          # update window "at scheduled restart"
        await self.start(force=False, reason=reason)

    def update_window_ok(self):
        """May automatic updates touch this server right now?"""
        w = self.settings.get("update_window", "empty")
        if not self.running():
            return w in ("empty", "stopped")
        return w == "empty" and self.state == "running" and self.tw is not None and not self.players

    # ---------------------------------------------------------- stats, RAM limit
    async def collect_stats(self, host, tick):
        s = dict(host)
        s.update(srv_cpu=0.0, srv_mem=0, srv_threads=0)
        if self.running():
            try:
                root = psutil.Process(self.proc.pid)
                cpu = mem = thr = 0
                alive = {}
                for p in [root] + root.children(recursive=True):
                    pp = self.procs_cache.get(p.pid) or p
                    alive[p.pid] = pp
                    try:
                        cpu += pp.cpu_percent(None)
                        mem += pp.memory_info().rss
                        thr += pp.num_threads()
                    except psutil.Error:
                        pass
                self.procs_cache = alive
                s.update(srv_cpu=round(cpu / NCPU, 1), srv_cpu_core=round(cpu, 1), srv_mem=mem, srv_threads=thr)
            except psutil.Error:
                pass
        else:
            self.procs_cache = {}
        self.last_stats = s
        self.history.append({k: s.get(k) for k in ("t", "host_cpu", "host_mem", "srv_cpu", "srv_mem")})
        self.publish({"type": "stats", **s})
        if self.state == "running":
            await self._ram_guard(s["srv_mem"])
            self._track_save_version()
        if self.state == "running" and self.tw:
            try:
                if tick % 3 == 0:
                    await self.refresh_players()
                if tick % 6 == 1:
                    for line in await self.command("gettime", timeout=3, quiet=True):
                        if line.startswith("Day"):
                            self.gametime = line.strip()
                    await self.refresh_mem()
                self.push_state()
            except web.HTTPException:
                pass

    async def _ram_guard(self, mem):
        lim = float(self.settings.get("ram_limit_gb") or 0)
        if lim <= 0:
            return
        self.ram_over = self.ram_over + 1 if mem > lim * 1024 ** 3 else 0
        if self.ram_over < 3 or now_ts() - self.ram_action_at < 1800:
            return
        self.ram_action_at = now_ts()
        gb = mem / 1024 ** 3
        if self.settings.get("ram_action") == "restart":
            self.note(f"RAM {gb:.1f} GB over the {lim:g} GB limit - graceful restart in 2 minutes")
            await self.say(f"Server memory is high - restart in 2 minutes")

            async def later():
                await asyncio.sleep(60)
                await self.say("Restart in 1 minute")
                await asyncio.sleep(60)
                if self.running():
                    await self.say("Restarting now, saving the world...", "FF4444")
                    await self.restart(reason="RAM limit")
            asyncio.create_task(later())
        else:
            self.note(f"Warning: RAM {gb:.1f} GB is over the {lim:g} GB limit")

    async def refresh_players(self):
        out = await self.command("lp", timeout=3, quiet=True)
        players = []
        for line in out:
            m = re.match(r"^\s*\d+\.\s+id=(\d+),\s+(.*?),\s+pos=", line)
            if not m:
                continue
            kv = dict(re.findall(r"(\w+)=(\([^)]*\)|[^,]+)", line))
            players.append({
                "entityid": m.group(1), "name": m.group(2), "level": kv.get("level"), "health": kv.get("health"),
                "deaths": kv.get("deaths"), "zombies": kv.get("zombies"), "score": kv.get("score"),
                "ping": kv.get("ping"), "ip": kv.get("ip"), "pltfmid": (kv.get("pltfmid") or "").strip(),
                "crossid": (kv.get("crossid") or "").strip(), "pos": kv.get("pos"),
            })
        self.players = players
        return players

    async def refresh_mem(self):
        for line in await self.command("mem", timeout=3, quiet=True):
            if "FPS" in line:
                d = {}
                for k, rx in (("fps", r"FPS:\s*([\d.]+)"), ("heap", r"Heap:\s*([\d.]+)MB"),
                              ("rss", r"RSS:\s*([\d.]+)MB"), ("chunks", r"Chunks:\s*(\d+)"),
                              ("zombies", r"Zom:\s*(\d+)"), ("entities", r"Ent:\s*(\d+)"),
                              ("items", r"Items:\s*(\d+)")):
                    m = re.search(rx, line)
                    if m:
                        d[k] = m.group(1)
                self.meminfo = d

    # ---------------------------------------------------------- backups
    def list_backups(self):
        out = []
        for f in sorted(self.backups.glob("*.tar.zst"), reverse=True):
            st = f.stat()
            kind = next((k for k in ("auto", "pre-restore", "pre-update", "pre-import") if f"_{k}" in f.name), "manual")
            out.append({"name": f.name, "size": st.st_size, "mtime": st.st_mtime, "kind": kind})
        return out

    async def create_backup(self, kind="manual"):
        async with self.backup_lock:
            members = [m for m in ("userdata/Saves", "userdata/Mods", "userdata/Mods_disabled", "config", "mods.json")
                       if (self.dir / m).exists()]
            if self.settings["backup_include_worlds"] and (self.userdata / "GeneratedWorlds").exists():
                members.append("userdata/GeneratedWorlds")
            if not (self.userdata / "Saves").exists():
                raise web.HTTPConflict(text="Nothing to back up yet (no saved games)")
            self.set_busy(f"Backup ({kind})")
            try:
                if self.tw:
                    await self.command("saveworld", timeout=20, idle=2, quiet=True)
                    await asyncio.sleep(3)
                name = f"{stamp()}_{kind}.tar.zst"
                part = self.backups / (name + ".part")
                cmd = ["nice", "-n", "19", "ionice", "-c", "3", "tar", "--zstd", "-cf", str(part),
                       "-C", str(self.dir)] + members
                bcpu = cpu_list(self.settings["backup_cpus"], str(NCPU - 1))
                if bcpu and shutil.which("taskset"):
                    cmd = ["taskset", "-c", bcpu] + cmd
                t0 = time.monotonic()
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.STDOUT)
                out, _ = await proc.communicate()
                if proc.returncode not in (0, 1):     # 1 = a file changed while reading (game running) - fine
                    part.unlink(missing_ok=True)
                    raise web.HTTPInternalServerError(text="tar failed: " + out.decode(errors="replace")[-500:])
                os.replace(part, self.backups / name)
                size = (self.backups / name).stat().st_size
                self.note(f"Backup done: {name} ({size / 1048576:.1f} MB, {time.monotonic() - t0:.0f} s, core {bcpu})")
                self.save_pstate(last_backup=now_ts(), **({"last_auto_backup": now_ts()} if kind == "auto" else {}))
                if kind == "auto":
                    autos = [b for b in self.list_backups() if b["kind"] == "auto"]
                    for b in autos[int(self.settings["backup_keep"]):]:
                        (self.backups / b["name"]).unlink(missing_ok=True)
                return name
            finally:
                self.set_busy("")

    async def restore_backup(self, name):
        f = self.backups / Path(name).name
        if not f.exists():
            raise web.HTTPNotFound(text="Backup not found")
        if self.running():
            raise web.HTTPConflict(text="Stop the server before restoring")
        if (self.userdata / "Saves").exists():
            await self.create_backup("pre-restore")
        async with self.backup_lock:
            self.set_busy("Restoring backup")
            try:
                tmp = Path(tempfile.mkdtemp(dir=self.dir, prefix=".restore_"))
                proc = await asyncio.create_subprocess_exec("tar", "--zstd", "-xf", str(f), "-C", str(tmp),
                                                            stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.STDOUT)
                out, _ = await proc.communicate()
                if proc.returncode != 0:
                    shutil.rmtree(tmp, ignore_errors=True)
                    raise web.HTTPInternalServerError(text="Extract failed: " + out.decode(errors="replace")[-300:])
                for m in ("userdata/Saves", "userdata/GeneratedWorlds", "userdata/Mods", "userdata/Mods_disabled",
                          "config", "mods.json"):
                    src = tmp / m
                    if src.exists():
                        dst = self.dir / m
                        if dst.is_dir():
                            await asyncio.to_thread(shutil.rmtree, dst)
                        elif dst.exists():
                            dst.unlink()
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src), str(dst))
                shutil.rmtree(tmp, ignore_errors=True)
                self.ensure_config()
                self.mods = Mods(self)
                self.note(f"Restored from {f.name}")
            finally:
                self.set_busy("")

    # ---------------------------------------------------------- import an existing world
    async def import_world(self, zpath: Path, version_label=None, overwrite=False):
        """ZIP with Saves/<World>/<Game> (folder containing main.ttw) and optionally
        GeneratedWorlds/<World> (map_info.xml / dtm.raw). Makes it the active world."""
        if self.running():
            raise web.HTTPConflict(text="Stop the server before importing a world")
        tmp = Path(tempfile.mkdtemp(dir=self.dir, prefix=".import_"))
        try:
            await asyncio.to_thread(safe_extract, zpath, tmp)
            saves = sorted({p.parent for p in tmp.rglob("main.ttw")}, key=lambda d: len(d.parts))
            gens = sorted({p.parent for pat in ("map_info.xml", "dtm.raw", "dtm_processed.raw") for p in tmp.rglob(pat)
                           if "Saves" not in p.parts}, key=lambda d: len(d.parts))
            if not saves:
                raise web.HTTPBadRequest(text="No saved game found (folder with main.ttw). Zip the folder "
                                              "%APPDATA%\\7DaysToDie\\Saves\\<World>\\<Game>")
            if (self.userdata / "Saves").exists() and not overwrite:
                for s in saves:
                    if (self.userdata / "Saves" / s.parent.name / s.name).exists():
                        raise web.HTTPConflict(text=f"Save {s.parent.name}/{s.name} already exists on this server")
            if (self.userdata / "Saves").exists():
                await self.create_backup("pre-import")
            imported = []
            for s in saves:
                world = s.parent.name if s.parent != tmp else "Imported"
                dst = self.userdata / "Saves" / world / s.name
                if dst.exists():
                    await asyncio.to_thread(shutil.rmtree, dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(s), str(dst))
                imported.append((world, s.name))
            for g in gens:
                dst = self.userdata / "GeneratedWorlds" / g.name
                if dst.exists():
                    await asyncio.to_thread(shutil.rmtree, dst)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(g), str(dst))
            world, game = imported[0]
            builtin = self.hub.builtin_worlds(self.branch)
            warnings = []
            if world not in builtin and not (self.userdata / "GeneratedWorlds" / world).exists():
                warnings.append(f"Map '{world}' is missing - add the folder %APPDATA%\\7DaysToDie\\GeneratedWorlds\\{world} to the ZIP")
            if self.cfg.exists():
                write_config_props(self.cfg, {"GameWorld": world, "GameName": game})
            if version_label:
                sm = dict(self.pstate.get("saves_meta") or {})
                for w, g in imported:
                    sm[f"{w}/{g}"] = {"created": version_label, "last": version_label, "imported": True}
                self.save_pstate(saves_meta=sm)
            self.note(f"World imported: {', '.join(f'{w}/{g}' for w, g in imported)}"
                      + (f" (made with {version_label})" if version_label else ""))
            return {"imported": [f"{w}/{g}" for w, g in imported], "maps": [g.name for g in gens], "warnings": warnings}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---------------------------------------------------------- scheduler
    async def schedule_tick(self):
        st = self.settings
        try:
            ivl = float(st.get("backup_interval_hours") or 0)
            if ivl > 0 and not self.busy:
                if not self.pstate.get("last_auto_backup"):
                    self.save_pstate(last_auto_backup=now_ts())
                cond = self.state == "running" if st["backup_only_when_running"] else True
                if cond and (self.userdata / "Saves").exists() and now_ts() - self.pstate["last_auto_backup"] >= ivl * 3600:
                    await self.create_backup("auto")
            await self.run_schedule()
        except web.HTTPException as e:
            self.note(f"Scheduler: {e.text}")
        except CompatError as e:
            self.note(f"Scheduler: not starting - {e.message}")
        except Exception as e:  # the scheduler must never die
            self.note(f"Scheduler error: {e!r}")

    async def run_schedule(self):
        nowd = dt.datetime.now()
        done = self.pstate.setdefault("sched_done", {})
        for r in self.settings.get("schedule") or []:
            if not r.get("enabled", True):
                continue
            try:
                h, m = parse_hhmm(r["time"])
            except (KeyError, ValueError):
                continue
            target = nowd.replace(hour=h, minute=m, second=0, microsecond=0)
            if target < nowd - dt.timedelta(minutes=5):
                target += dt.timedelta(days=1)
            if target.isoweekday() not in set(r.get("days") or []):
                continue
            key = target.strftime("%Y-%m-%d %H:%M")
            if done.get(r["id"]) == key:
                continue
            mins = (target - nowd).total_seconds() / 60
            act = r.get("action", "restart")
            if act in ("stop", "restart", "update_restart") and self.state == "running" and self.tw:
                for w in sorted({int(x) for x in r.get("warn") or []}, reverse=True):
                    wk = f"{r['id']}|{key}|{w}"
                    if 0 < mins <= w and wk not in self.warned:
                        self.warned.add(wk)
                        what = "shut down" if act == "stop" else "restart"
                        await self.say(f"Server will {what} in {w} min." + (f" {r['message']}" if r.get("message") else ""))
                        self.note(f"Warned players: {what} in {w} min")
            if mins > 0:
                continue
            done[r["id"]] = key
            self.save_pstate(sched_done=done)
            self.note(f"Schedule: {act} ({key})")
            if act == "start":
                if not self.running():
                    await self.start(reason="schedule")
            elif act == "stop":
                if self.running():
                    await self.say("Server is shutting down, saving the world...", "FF4444")
                    await asyncio.sleep(3)
                    await self.stop(user=True, reason="schedule")
            elif act in ("restart", "update_restart"):
                if self.running():
                    await self.say("Server is restarting, saving the world...", "FF4444")
                    await asyncio.sleep(3)
                    await self.restart(reason="schedule", update=act == "update_restart")
                elif act == "update_restart":
                    await self.hub.update_game(self.branch, reason="schedule")
            elif act == "backup" and (self.userdata / "Saves").exists():
                await self.create_backup("auto")


def validate_schedule(rules):
    if not isinstance(rules, list) or len(rules) > 50:
        raise web.HTTPBadRequest(text="Schedule: invalid rule list")
    out = []
    for r in rules:
        act = str(r.get("action", ""))
        if act not in ACTIONS:
            raise web.HTTPBadRequest(text=f"Schedule: unknown action {act}")
        try:
            parse_hhmm(str(r.get("time", "")))
        except ValueError:
            raise web.HTTPBadRequest(text="Schedule: time must be HH:MM")
        days = sorted({int(d) for d in r.get("days") or [] if 1 <= int(d) <= 7})
        if not days:
            raise web.HTTPBadRequest(text="Schedule: pick at least one day")
        warn = sorted({int(w) for w in (r.get("warn") or []) if 0 < int(w) <= 120}, reverse=True)
        out.append({"id": str(r.get("id") or secrets.token_hex(4))[:16], "enabled": bool(r.get("enabled", True)),
                    "days": days, "time": str(r["time"]), "action": act, "warn": warn,
                    "message": str(r.get("message", ""))[:120].replace('"', "'")})
    return out
