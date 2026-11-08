"""HTTP API."""
import asyncio
import json
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from aiohttp import web

from . import versions
from .instance import DEFAULT_SETTINGS, CompatError, validate_schedule
from .configmeta import catalog
from .presets import PRESETS
from .steam import check_branch
from .util import (DATA, INST_ROOT, PANEL_DIR, VERSIONS_DIR, dir_size, get_prop, read_config_props, rel, safe_extract,
                   safe_path, save_json, write_config_props)

HUB = None


def ok(**kw):
    return web.json_response({"ok": True, **kw})


def inst_of(request):
    return HUB.get(request.match_info["iid"])


def bg(coro, label, inst=None):
    """Run a long operation in the background, report errors to the console."""
    async def runner():
        try:
            await coro
        except CompatError as e:
            (inst.note if inst else HUB.broadcast)(f"{label}: {e.message}")
        except web.HTTPException as e:
            (inst.note if inst else HUB.broadcast)(f"{label}: {e.text}")
        except Exception as e:
            (inst.note if inst else HUB.broadcast)(f"{label}: error {e!r}")
    asyncio.create_task(runner())


@web.middleware
async def errors(request, handler):
    try:
        return await handler(request)
    except CompatError as e:
        return web.json_response({"error": e.message, "compat": e.compat}, status=409)
    except web.HTTPException as e:
        if e.status >= 400 and request.path.startswith("/api/"):
            return web.json_response({"error": e.text or e.reason}, status=e.status)
        raise
    except Exception as e:
        print(f"[7edcore] error {request.path}: {e!r}", flush=True)
        return web.json_response({"error": f"Internal error: {e}"}, status=500)


async def read_upload(request, dest_dir: Path, exts=(".zip",)):
    """Stream multipart files to dest_dir. Returns (paths, fields)."""
    reader = await request.multipart()
    files, fields = [], {}
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.filename:
            if exts and not part.filename.lower().endswith(exts):
                raise web.HTTPBadRequest(text=f"{part.filename}: expected {', '.join(exts)}")
            target = dest_dir / Path(part.filename).name
            with open(target, "wb") as f:
                while True:
                    chunk = await part.read_chunk(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            files.append(target)
        else:
            fields[part.name] = (await part.read()).decode()
    return files, fields


# ------------------------------------------------------------------ overview, global, game versions
async def h_overview(request):
    return web.json_response(HUB.overview())


async def h_presets(request):
    return web.json_response({"presets": PRESETS})


async def h_configmeta(request):
    return web.json_response(catalog())


async def h_global_get(request):
    g = HUB.glob
    return web.json_response({"github_token_set": bool(g.get("github_token")), "nexus_key_set": bool(g.get("nexus_key")),
                              "password_env": bool(os.environ.get("PANEL_PASSWORD"))})


async def h_global_set(request):
    d = await request.json()
    for k in ("github_token", "nexus_key"):
        if k in d:
            HUB.glob[k] = str(d[k]).strip()
    save_json(PANEL_DIR / "global.json", HUB.glob, mode=0o600)
    return ok()


async def h_versions(request):
    if request.query.get("refresh") == "1":
        await HUB.steam.fetch_branches(force=True)
    elif not HUB.steam.cache["list"]:
        try:
            await HUB.steam.fetch_branches()
        except web.HTTPException as e:
            return web.json_response({**HUB.steam.status(), "error": e.text})
    return web.json_response(HUB.steam.status())


async def h_version_action(request):
    branch = check_branch(request.match_info["branch"])
    act = request.match_info["act"]
    if act in ("install", "validate"):
        if not HUB.steam.queue(branch, validate=act == "validate"):
            raise web.HTTPConflict(text=f"{branch} is already queued")
    elif act == "update":
        bg(HUB.update_game(branch, reason="manual"), "Game update")
    elif act == "remove":
        HUB.steam.remove(branch)
    else:
        raise web.HTTPNotFound()
    return ok()


async def h_updates_check(request):
    """Check game + mod updates now (normally every 30 min / 6 h)."""
    await HUB.check_updates(force_branches=True)
    for i in list(HUB.instances.values()):
        if any(m.get("source") for m in i.mods.list()):
            try:
                await HUB.check_mods(i)
            except web.HTTPException as e:
                i.note(f"Mod check failed: {e.text}")
    await HUB.check_panel_update()
    HUB.push_all()
    return ok(notices={i.id: i.notices for i in HUB.instances.values()}, panel=HUB.panel_update)


# ------------------------------------------------------------------ servers
async def h_create(request):
    d = await request.json()
    branch = d.get("game_version") or None
    if branch:
        check_branch(branch)
    inst = HUB.create(str(d.get("name", "")), clone_from=d.get("clone_from") or None, branch=branch)
    if not HUB.steam.installed(inst.branch):
        HUB.steam.queue(inst.branch)
    return ok(id=inst.id)


async def h_rename(request):
    i = inst_of(request)
    name = str((await request.json()).get("name", "")).strip()[:40]
    if not name:
        raise web.HTTPBadRequest(text="Enter a name")
    i.name = name
    HUB.save_registry()
    i.push_state()
    return ok()


async def h_delete(request):
    i = inst_of(request)
    if str((await request.json()).get("confirm", "")).strip() != i.name:
        raise web.HTTPBadRequest(text="Type the exact server name to delete it")
    await HUB.delete(i.id)
    return ok()


async def h_status(request):
    i = inst_of(request)
    return web.json_response({**i.status(), "stats": i.last_stats, "settings": i.settings})


async def h_action(request):
    i = inst_of(request)
    act = request.match_info["act"]
    force = request.query.get("force") == "1"
    if act == "start":
        if i.running():
            raise web.HTTPConflict(text="Server is already running")
        c = i.compat_check()
        if c["level"] in ("major", "downgrade") and not force:
            raise CompatError("The active save was made with a different game version", c)
        if not HUB.steam.installed(i.branch):
            raise web.HTTPConflict(text=f"Game version {i.branch} is not installed")
        bg(i.start(force=True), "Start", i)
    elif act == "stop":
        bg(i.stop(user=True), "Stop", i)
    elif act == "restart":
        bg(i.restart(), "Restart", i)
    elif act == "kill":
        await i.kill()
    else:
        raise web.HTTPNotFound()
    return ok()


async def h_set_version(request):
    i = inst_of(request)
    d = await request.json()
    branch = check_branch(str(d.get("branch", "")))
    if i.running():
        raise web.HTTPConflict(text="Stop the server before changing the game version")
    label = HUB.steam.version_label(branch) if HUB.steam.installed(branch) else None
    if not label:
        b = HUB.steam.branch(branch)
        v = (HUB.steam.version_of_build(b["build"]) if b and branch == "public" else None) or \
            versions.parse((b or {}).get("description", "")) or versions.parse(branch)
        label = v["label"] if v else None
    c = i.compat_check(label)
    if c["level"] in ("major", "downgrade") and not d.get("force"):
        raise CompatError("The active save does not match this game version", c)
    i.settings["game_version"] = branch
    i.save_settings()
    i.note(f"Game version set to {branch} ({label or '?'})")
    if not HUB.steam.installed(branch):
        HUB.steam.queue(branch)
    i.push_state()
    return ok(compat=c)


async def h_compat(request):
    i = inst_of(request)
    branch = request.query.get("branch") or i.branch
    check_branch(branch)
    label = HUB.steam.version_label(branch) if HUB.steam.installed(branch) else None
    if not label:
        b = HUB.steam.branch(branch)
        v = (HUB.steam.version_of_build(b["build"]) if b and branch == "public" else None) or \
            versions.parse((b or {}).get("description", "")) or versions.parse(branch)
        label = v["label"] if v else None
    return web.json_response(i.compat_check(label))


async def h_command(request):
    i = inst_of(request)
    d = await request.json()
    cmd = str(d.get("command", "")).strip()
    if not cmd or "\n" in cmd or "\r" in cmd:
        raise web.HTTPBadRequest(text="Invalid command")
    return ok(output=await i.command(cmd, timeout=float(d.get("timeout", 5))))


async def h_players(request):
    i = inst_of(request)
    if i.tw:
        await i.refresh_players()
    return web.json_response({"players": i.players})


async def h_events(request):
    i = inst_of(request)
    resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})
    await resp.prepare(request)
    q = asyncio.Queue()
    i.subscribers.add(q)
    try:
        snap = {"type": "snapshot", "status": i.status(), "console": list(i.console_buf)[-800:],
                "history": list(i.history), "stats": i.last_stats}
        await resp.write(f"data: {json.dumps(snap, ensure_ascii=False)}\n\n".encode())
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=20)
                await resp.write(f"data: {msg}\n\n".encode())
            except asyncio.TimeoutError:
                await resp.write(b": ping\n\n")
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        i.subscribers.discard(q)
    return resp


async def h_settings_get(request):
    return web.json_response(inst_of(request).settings)


CHOICES = {"autostart": ("off", "always", "last"), "ram_action": ("warn", "restart"),
           "game_updates": ("off", "notify", "patch", "minor"), "mod_updates": ("off", "notify", "auto"),
           "update_window": ("empty", "stopped", "restart")}


async def h_settings_set(request):
    i = inst_of(request)
    d = await request.json()
    for k, v in d.items():
        if k not in DEFAULT_SETTINGS or k == "game_version":
            continue
        if k == "schedule":
            i.settings[k] = validate_schedule(v)
            continue
        base = DEFAULT_SETTINGS[k]
        if isinstance(base, bool):
            v = bool(v)
        elif isinstance(base, (int, float)) and not isinstance(base, bool):
            try:
                v = float(v) if k == "ram_limit_gb" else int(float(v))
            except (TypeError, ValueError):
                raise web.HTTPBadRequest(text=f"{k}: number expected")
        else:
            v = str(v).strip()
        if k in CHOICES and v not in CHOICES[k]:
            raise web.HTTPBadRequest(text=f"{k}: one of {', '.join(CHOICES[k])}")
        i.settings[k] = v
    i.save_settings()
    i.push_state()
    return ok(settings=i.settings)


# ------------------------------------------------------------------ server config
async def h_config_get(request):
    i = inst_of(request)
    return web.json_response({"exists": i.cfg.exists(), "path": rel(i.cfg),
                              "props": [{"name": n, "value": v, "comment": c} for n, v, c in read_config_props(i.cfg)]})


async def h_config_set(request):
    i = inst_of(request)
    if not i.cfg.exists():
        raise web.HTTPConflict(text="No configuration yet - install the game version first")
    changes = {str(k): str(v) for k, v in ((await request.json()).get("changes") or {}).items()}
    changes.pop("UserDataFolder", None)
    changes.pop("TelnetEnabled", None)
    shutil.copy2(i.cfg, i.cfg.with_suffix(".xml.bak"))
    write_config_props(i.cfg, changes)
    try:
        ET.parse(i.cfg)
    except ET.ParseError as e:
        shutil.copy2(i.cfg.with_suffix(".xml.bak"), i.cfg)
        raise web.HTTPBadRequest(text=f"Invalid value, nothing saved: {e}")
    i.note(f"Configuration saved ({len(changes)} changes) - applies after restart")
    i.push_state()
    return ok()


async def h_preset_apply(request):
    i = inst_of(request)
    pid = str((await request.json()).get("id", ""))
    pr = next((p for p in PRESETS if p["id"] == pid), None)
    if not pr:
        raise web.HTTPNotFound(text="Unknown preset")
    if not i.cfg.exists():
        raise web.HTTPConflict(text="No configuration yet - install the game version first")
    have = {n for n, _, _ in read_config_props(i.cfg)}
    ch = {k: v for k, v in pr["values"].items() if k in have}
    write_config_props(i.cfg, ch)
    i.settings["preset"] = pid
    i.save_settings()
    i.note(f"Preset applied: {pr['name']['en']} ({len(ch)} settings) - applies after restart")
    i.push_state()
    return ok(applied=ch, skipped=sorted(set(pr["values"]) - have))


# ------------------------------------------------------------------ worlds
async def h_worlds(request):
    i = inst_of(request)

    def collect():
        gen, saves = [], []
        gd = i.userdata / "GeneratedWorlds"
        if gd.exists():
            for d in sorted(gd.iterdir()):
                if d.is_dir():
                    gen.append({"name": d.name, "size": dir_size(d), "mtime": d.stat().st_mtime})
        sd = i.userdata / "Saves"
        meta = i.pstate.get("saves_meta") or {}
        if sd.exists():
            for w in sorted(sd.iterdir()):
                if w.is_dir():
                    for g in sorted(w.iterdir()):
                        if g.is_dir():
                            m = meta.get(f"{w.name}/{g.name}") or {}
                            saves.append({"world": w.name, "game": g.name, "size": dir_size(g), "mtime": g.stat().st_mtime,
                                          "created": m.get("created"), "last": m.get("last")})
        return gen, saves
    gen, saves = await asyncio.to_thread(collect)
    cur = {k: get_prop(i.cfg, k) for k in ("GameWorld", "GameName", "WorldGenSeed", "WorldGenSize")}
    return web.json_response({"current": cur, "generated": gen, "saves": saves, "builtin": HUB.builtin_worlds(i.branch),
                              "active": i.active_save(), "game": i.game_version_label(), "branch": i.branch})


async def h_world_select(request):
    i = inst_of(request)
    d = await request.json()
    ch = {}
    for k in ("GameWorld", "GameName", "WorldGenSeed", "WorldGenSize"):
        if d.get(k) not in (None, ""):
            v = str(d[k]).strip()
            if k in ("GameWorld", "GameName") and not re.fullmatch(r"[\w \-.]+", v):
                raise web.HTTPBadRequest(text=f"{k}: letters, numbers, space, - _ . only")
            ch[k] = v
    if not ch:
        raise web.HTTPBadRequest(text="Nothing to change")
    if not i.cfg.exists():
        raise web.HTTPConflict(text="Install the game version first")
    write_config_props(i.cfg, ch)
    i.note("World set: " + ", ".join(f"{k}={v}" for k, v in ch.items()) + " - applies after (re)start")
    i.push_state()
    return ok(compat=i.compat_check())


async def h_world_delete(request):
    i = inst_of(request)
    if i.running():
        raise web.HTTPConflict(text="Stop the server first")
    d = await request.json()
    if d.get("type") == "save":
        p = i.userdata / "Saves" / Path(d["world"]).name / Path(d["game"]).name
    elif d.get("type") == "generated":
        p = i.userdata / "GeneratedWorlds" / Path(d["world"]).name
    else:
        raise web.HTTPBadRequest()
    if not p.is_dir():
        raise web.HTTPNotFound(text="Not found")
    await asyncio.to_thread(shutil.rmtree, p)
    i.note(f"Deleted: {rel(p)}")
    return ok()


async def h_import(request):
    i = inst_of(request)
    tmp = Path(tempfile.mkdtemp(dir=i.dir, prefix=".up_"))
    try:
        files, fields = await read_upload(request, tmp)
        if not files:
            raise web.HTTPBadRequest(text="Choose a ZIP file")
        v = versions.parse(fields.get("version", ""))
        return ok(**await i.import_world(files[0], v["label"] if v else None, fields.get("overwrite") == "1"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ mods
async def h_mods(request):
    i = inst_of(request)
    return web.json_response({"mods": await asyncio.to_thread(i.mods.list), "path": rel(i.mods.on),
                              "game": i.game_version_label(), "running": i.state in ("running", "starting"),
                              "policy": i.settings["mod_updates"]})


async def h_mods_upload(request):
    i = inst_of(request)
    tmp = Path(tempfile.mkdtemp(dir=i.dir, prefix=".up_"))
    try:
        files, fields = await read_upload(request, tmp)
        src = fields.get("source", "").strip()
        report = []
        for f in files:
            from .mods import parse_source
            report += await i.mods.install_zip(f, source=parse_source(src) if src else None)
        i.note("Mods installed: " + ", ".join(r["folder"] for r in report) + " - applies after restart")
        return ok(report=report)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def h_mods_install(request):
    i = inst_of(request)
    src = str((await request.json()).get("source", ""))
    report = await i.mods.install_from(src, HUB.glob.get("github_token"))
    i.note("Mods installed: " + ", ".join(r["folder"] for r in report) + " - applies after restart")
    return ok(report=report)


async def h_mod_op(request):
    i = inst_of(request)
    folder, op = request.match_info["folder"], request.match_info["op"]
    if op == "check":
        return ok(result=await i.mods.check(folder, HUB.glob.get("github_token"), HUB.glob.get("nexus_key")))
    if op == "update":
        if i.running():
            raise web.HTTPConflict(text="Stop the server before updating mods")
        if (i.userdata / "Saves").exists():
            await i.create_backup("pre-update")
        rep = await i.mods.update(folder, HUB.glob.get("github_token"))
        i.note(f"Mod updated: {folder}")
        await HUB.check_mods(i)
        return ok(report=rep)
    if op == "toggle":
        en = i.mods.toggle(folder)
        i.note(f"Mod {'enabled' if en else 'disabled'}: {folder}")
        return ok(enabled=en)
    if op == "delete":
        i.mods.delete(folder)
        i.note(f"Mod deleted: {folder}")
        return ok()
    if op == "source":
        i.mods.set_source(folder, str((await request.json()).get("source", "")))
        return ok()
    raise web.HTTPNotFound()


async def h_mods_check_all(request):
    i = inst_of(request)
    return ok(updates=await HUB.check_mods(i))


# ------------------------------------------------------------------ backups
async def h_backups(request):
    i = inst_of(request)
    return web.json_response({"backups": i.list_backups(), "busy": i.busy, "path": rel(i.backups)})


async def h_backups_op(request):
    i = inst_of(request)
    op = request.match_info["op"]
    d = await request.json() if request.can_read_body else {}
    if op == "create":
        bg(i.create_backup("manual"), "Backup", i)
    elif op == "restore":
        bg(i.restore_backup(str(d.get("name", ""))), "Restore", i)
    elif op == "delete":
        f = i.backups / Path(str(d.get("name", ""))).name
        if not f.exists():
            raise web.HTTPNotFound()
        f.unlink()
    else:
        raise web.HTTPNotFound()
    return ok()


# ------------------------------------------------------------------ files (whole /data)
PROTECTED = None


async def h_files_list(request):
    p = safe_path(request.query.get("path", "/"))
    if not p.is_dir():
        raise web.HTTPNotFound(text="Folder not found")
    items = []
    for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        try:
            st = e.stat()
            items.append({"name": e.name, "dir": e.is_dir(), "size": st.st_size, "mtime": st.st_mtime})
        except OSError:
            pass
    return web.json_response({"path": rel(p), "items": items})


async def h_files_read(request):
    p = safe_path(request.query.get("path", ""))
    if not p.is_file():
        raise web.HTTPNotFound(text="File not found")
    if p.stat().st_size > 3 * 1024 * 1024:
        raise web.HTTPRequestEntityTooLarge(max_size=3 * 1024 * 1024, actual_size=p.stat().st_size,
                                            text="Too large for the editor - download it")
    raw = p.read_bytes()
    if b"\x00" in raw[:8192]:
        raise web.HTTPUnsupportedMediaType(text="Binary file - download it")
    return web.json_response({"path": rel(p), "content": raw.decode("utf-8", "replace")})


async def h_files_write(request):
    d = await request.json()
    p = safe_path(d.get("path", ""))
    if p.is_dir():
        raise web.HTTPBadRequest(text="That is a folder")
    if p.exists():
        shutil.copy2(p, p.with_name(p.name + ".bak"))
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(d.get("content", ""), encoding="utf-8")
    os.replace(tmp, p)
    if p.suffix == ".xml":
        try:
            ET.parse(p)
        except ET.ParseError as e:
            bak = p.with_name(p.name + ".bak")
            if bak.exists():
                shutil.copy2(bak, p)
                raise web.HTTPBadRequest(text=f"Invalid XML, previous version restored: {e}")
    return ok()


async def h_files_download(request):
    p = safe_path(request.query.get("path", ""))
    if not p.is_file():
        raise web.HTTPNotFound(text="File not found")
    return web.FileResponse(p, headers={"Content-Disposition": f'attachment; filename="{p.name}"'})


async def h_files_upload(request):
    dest = safe_path(request.query.get("path", "/"))
    if not dest.is_dir():
        raise web.HTTPNotFound(text="Target folder not found")
    files, _ = await read_upload(request, dest, exts=None)
    return ok(saved=[f.name for f in files])


async def h_files_op(request):
    op = request.match_info["op"]
    d = await request.json()
    p = safe_path(d.get("path", ""))
    if p in (DATA, VERSIONS_DIR, INST_ROOT, PANEL_DIR) or p.parent == VERSIONS_DIR or p.parent == INST_ROOT:
        raise web.HTTPForbidden(text="Protected folder - use the panel for this")
    if op == "mkdir":
        p.mkdir(parents=True, exist_ok=False)
    elif op == "delete":
        await asyncio.to_thread(shutil.rmtree, p) if p.is_dir() else p.unlink()
    elif op == "rename":
        new = str(d.get("newname", "")).strip()
        if not new or "/" in new or new in (".", ".."):
            raise web.HTTPBadRequest(text="Invalid name")
        p.rename(p.with_name(new))
    elif op == "extract":
        if not zipfile.is_zipfile(p):
            raise web.HTTPBadRequest(text="Not a ZIP file")
        await asyncio.to_thread(safe_extract, p, p.parent)
    else:
        raise web.HTTPNotFound()
    return ok()


def routes(app):
    r = app.router
    r.add_get("/api/overview", h_overview)
    r.add_get("/api/presets", h_presets)
    r.add_get("/api/configmeta", h_configmeta)
    r.add_get("/api/global", h_global_get)
    r.add_post("/api/global", h_global_set)
    r.add_get("/api/versions", h_versions)
    r.add_post("/api/versions/{branch}/{act}", h_version_action)
    r.add_post("/api/updates/check", h_updates_check)
    r.add_post("/api/servers", h_create)
    r.add_get("/api/files", h_files_list)
    r.add_get("/api/files/read", h_files_read)
    r.add_post("/api/files/write", h_files_write)
    r.add_get("/api/files/download", h_files_download)
    r.add_post("/api/files/upload", h_files_upload)
    r.add_post("/api/files/{op}", h_files_op)
    p = "/api/s/{iid}"
    r.add_post(p + "/rename", h_rename)
    r.add_post(p + "/delete", h_delete)
    r.add_get(p + "/status", h_status)
    r.add_get(p + "/events", h_events)
    r.add_post(p + "/server/{act}", h_action)
    r.add_post(p + "/version", h_set_version)
    r.add_get(p + "/compat", h_compat)
    r.add_post(p + "/command", h_command)
    r.add_get(p + "/players", h_players)
    r.add_get(p + "/settings", h_settings_get)
    r.add_post(p + "/settings", h_settings_set)
    r.add_get(p + "/config", h_config_get)
    r.add_post(p + "/config", h_config_set)
    r.add_post(p + "/preset", h_preset_apply)
    r.add_get(p + "/worlds", h_worlds)
    r.add_post(p + "/worlds/select", h_world_select)
    r.add_post(p + "/worlds/delete", h_world_delete)
    r.add_post(p + "/worlds/import", h_import)
    r.add_get(p + "/mods", h_mods)
    r.add_post(p + "/mods/upload", h_mods_upload)
    r.add_post(p + "/mods/install", h_mods_install)
    r.add_post(p + "/mods/check", h_mods_check_all)
    r.add_post(p + "/mods/{folder}/{op}", h_mod_op)
    r.add_get(p + "/backups", h_backups)
    r.add_post(p + "/backups/{op}", h_backups_op)
