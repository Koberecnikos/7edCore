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

from . import selfupdate, versions
from .instance import DEFAULT_SETTINGS, CompatError, validate_schedule
from .configmeta import catalog
from . import modlets, presets, sandbox
from .steam import check_branch
from .util import (DATA, load_json, INST_ROOT, PANEL_DIR, VERSIONS_DIR, dir_size, get_prop, read_config_props, rel, safe_extract,
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
    from .auth import can_see
    ov = HUB.overview()
    ov["instances"] = [x for x in ov["instances"] if can_see(request["user"], x["id"])]
    return web.json_response(ov)


async def h_presets(request):
    return web.json_response(presets.public())


async def h_configmeta(request):
    return web.json_response(catalog())


async def h_global_get(request):
    g = HUB.glob
    return web.json_response({"self_update": selfupdate.status(),"github_token_set": bool(g.get("github_token")), "nexus_key_set": bool(g.get("nexus_key")),
                              "password_env": bool(os.environ.get("PANEL_PASSWORD"))})


async def h_global_set(request):
    d = await request.json()
    for k in ("github_token", "nexus_key"):
        if k in d:
            HUB.glob[k] = str(d[k]).strip()
    save_json(PANEL_DIR / "global.json", HUB.glob, mode=0o600)
    return ok()


async def h_selfupdate(request):
    d = await request.json()
    if d.get("policy") not in selfupdate.POLICIES:
        raise web.HTTPBadRequest(text="policy: auto, notify or off")
    selfupdate.set_policy(d["policy"])
    return ok()


async def h_selfupdate_now(request):
    if not selfupdate.status()["updater"]:
        raise web.HTTPConflict(text="The 7edCore updater is not installed on this host")
    selfupdate.request()
    HUB.broadcast("7edCore update requested - the panel will restart shortly")
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
    from . import auth
    for u in auth.USERS.values():
        if isinstance(u["servers"], list) and i.id in u["servers"]:
            u["servers"].remove(i.id)
    auth.save_users()
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


async def h_quick(request):
    """Per-server shortcuts."""
    i = inst_of(request)
    act = request.match_info["act"]
    d = await request.json() if request.can_read_body else {}
    mins = float(d.get("minutes", 5) or 0)
    if act == "saveworld":
        if not i.tw:
            raise web.HTTPConflict(text="Server is not running")
        out = await i.command("saveworld", timeout=30)
        i.note("World saved")
        return ok(output=out)
    if act == "say":
        msg = str(d.get("message", "")).strip()[:200]
        if not msg or not i.tw:
            raise web.HTTPBadRequest(text="Server must run and message must not be empty")
        await i.say(msg, "FFFFFF")
        i.note(f"Broadcast: {msg}")
        return ok()
    if act == "restart" and i.running():
        await i.countdown(mins, "restart", lambda: i.restart(reason="manual"))
    elif act == "stop" and i.running():
        await i.countdown(mins, "shut down", lambda: i.stop(user=True, reason="manual"))
    elif act == "update_game":
        info = HUB.steam.update_info(i.branch)
        if not info.get("available"):
            raise web.HTTPConflict(text="The game is up to date")
        if i.running() and mins > 0:
            await i.countdown(mins, "update", lambda: HUB.update_game(i.branch, reason="manual"))
        else:
            bg(HUB.update_game(i.branch, reason="manual"), "Game update", i)
    elif act == "update_mods":
        if i.running() and mins > 0:
            await i.countdown(mins, "update mods", lambda: HUB.update_mods_now(i))
        else:
            bg(HUB.update_mods_now(i), "Mod update", i)
    elif act == "update_all":
        async def all_():
            was = i.running()
            if was:
                await i.stop(user=False, reason="update")
            if HUB.steam.update_info(i.branch).get("available"):
                await HUB.update_game(i.branch, reason="manual")
            await HUB.update_mods_now(i)
            if was:
                await i.start(reason="after update")
        if i.running() and mins > 0:
            await i.countdown(mins, "update", all_)
        else:
            bg(all_(), "Update", i)
    elif act == "cancel":
        if not i.cancel_pending():
            raise web.HTTPConflict(text="Nothing is pending")
    elif act == "check":
        await HUB.check_updates(force_branches=True)
        if any(m.get("source") for m in i.mods.list()):
            await HUB.check_mods(i)
        i.push_state()
        return ok(notices=i.notices)
    else:
        raise web.HTTPBadRequest(text="Unknown or not possible now")
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


def _one_preset(d):
    if d.get("tier"):
        try:
            return presets.roll(str(d["tier"]), d.get("seed"))
        except ValueError as e:
            raise web.HTTPBadRequest(text=str(e))
    pr = next((p for p in presets.PRESETS if p["id"] == str(d.get("id", ""))), None)
    if not pr:
        raise web.HTTPNotFound(text=f"Unknown preset {d.get('id')}")
    return pr


def preset_from_request(d):
    """One preset, a random roll, or a stack of them (first = highest priority)."""
    if "stack" not in d:
        return _one_preset(d)
    items = d.get("stack") or []
    if not isinstance(items, list) or not 1 <= len(items) <= 12:
        raise web.HTTPBadRequest(text="Pick 1-12 presets to combine")
    parts = [_one_preset(x) for x in items]
    if len(parts) == 1:
        return parts[0]
    values, legacy, modlets_, source, overridden = {}, {}, [], {}, []
    for pr in reversed(parts):                       # lowest priority first, higher ones overwrite
        for k, v in pr["values"].items():
            if k in source and values[k] != v:
                overridden.append({"key": k, "loser": source[k], "winner": pr["name"]})
            values[k] = v
            source[k] = pr["name"]
        legacy.update(pr.get("legacy") or {})
        modlets_ += [m for m in pr.get("modlets") or [] if m not in modlets_]
    return {"id": "stack", "icon": "🧩", "level": max(p["level"] for p in parts),
            "tier": max((p["tier"] for p in parts), key=["easy", "medium", "hard", "extreme"].index),
            "name": {lang: " + ".join(p["name"][lang] for p in parts) for lang in ("en", "cs")},
            "desc": {lang: " · ".join(p["name"][lang] for p in parts) for lang in ("en", "cs")},
            "values": values, "legacy": legacy, "modlets": modlets_, "reset_all": any(p["id"] == "standard" for p in parts),
            "stack": [{"id": p["id"], "seed": p.get("seed"), "tier": p["tier"] if "seed" in p else None,
                       "name": p["name"], "icon": p["icon"]} for p in parts],
            "source": source, "overridden": overridden}


def plan_preset(i, pr):
    """What applying a preset changes on this server: serverconfig props, SandboxCode, modlets."""
    if not i.cfg.exists():
        raise web.HTTPConflict(text="No configuration yet - install the game version first")
    props = {n: v for n, v, _ in read_config_props(i.cfg)}
    sb_mode = "SandboxCode" in props
    changes, diff, skipped = {}, [], []
    if sb_mode:
        cur = sandbox.full(props.get("SandboxCode", ""))
        new = dict(cur)
        # undo the previous preset (or everything presets touch for "standard"), keep the rest
        for k in (presets.managed_keys() if pr["id"] == "standard" or pr.get("reset_all") else i.settings.get("preset_keys") or []):
            if k in sandbox.OPTIONS:
                new[k] = sandbox.OPTIONS[k]["default"]
        for k, v in pr["values"].items():
            new[k] = sandbox.index_for(k, v)
        for k in sorted(set(new), key=lambda n: sandbox.OPTIONS[n]["id"]):
            if new[k] != cur[k]:
                diff.append({"key": k, "label": sandbox.OPTIONS[k]["label"], "from": (pr.get("source") or {}).get(k),
                             "old": sandbox.value_label(k, cur[k]), "new": sandbox.value_label(k, new[k])})
        code = sandbox.encode(new)
        if code != (props.get("SandboxCode") or "A"):
            changes["SandboxCode"] = code
    else:
        target = {}
        for k in (presets.managed_keys() if pr["id"] == "standard" or pr.get("reset_all") else i.settings.get("preset_keys") or []):
            if k in presets.LEGACY:
                prop, conv = presets.LEGACY[k]
                o = sandbox.OPTIONS[k]
                target[prop] = conv(sandbox.values(k)[o["default"]])
        if pr["id"] == "standard" or pr.get("reset_all"):
            target.update({"GameDifficulty": "1", "EnemyDifficulty": "0"})
        for k, v in pr["values"].items():
            if k in presets.LEGACY:
                prop, conv = presets.LEGACY[k]
                target[prop] = conv(v)
            else:
                skipped.append(k)
        target.update(pr.get("legacy") or {})
        for k, v in target.items():
            if k not in props:
                continue
            if props[k] != v:
                changes[k] = v
                diff.append({"key": k, "label": k, "old": props[k], "new": v})
    mods = modlets.applicable(pr.get("modlets") or [], sb_mode)
    return {"preset": {k: pr[k] for k in ("id", "icon", "level", "tier", "name", "desc", "stack") if k in pr}
            | ({"seed": pr["seed"], "twists": pr["twists"], "score": pr["score"]} if "seed" in pr else {}),
            "sandbox": sb_mode, "changes": changes, "diff": diff, "skipped": skipped, "modlets": mods,
            "modlet_desc": [modlets.MODLETS[m]["desc"] for m in mods], "overridden": pr.get("overridden") or []}


async def h_preset_preview(request):
    i = inst_of(request)
    return web.json_response(plan_preset(i, preset_from_request(await request.json())))


async def h_preset_apply(request):
    i = inst_of(request)
    pr = preset_from_request(await request.json())
    plan = plan_preset(i, pr)
    if plan["changes"]:
        shutil.copy2(i.cfg, i.cfg.with_suffix(".xml.bak"))
        write_config_props(i.cfg, plan["changes"])
    modlets.write(i.mods.on, plan["modlets"])
    i.settings["preset"] = pr["id"] + (f"#{pr['seed']}" if "seed" in pr else "")
    i.settings["preset_keys"] = sorted(pr["values"])
    i.settings["preset_stack"] = [{"id": x["id"], "seed": x["seed"], "tier": x["tier"]} for x in pr["stack"]] \
        if "stack" in pr else [{"id": pr["id"], "seed": pr.get("seed"), "tier": pr["tier"] if "seed" in pr else None}]
    i.save_settings()
    i.note(f"Preset applied: {pr['name']['en']} ({len(plan['diff'])} settings"
           + (f", modlet: {', '.join(plan['modlets'])}" if plan["modlets"] else "") + ") - applies after restart")
    i.push_state()
    return ok(**plan)


async def h_sandbox_get(request):
    i = inst_of(request)
    code = get_prop(i.cfg, "SandboxCode", None) if i.cfg.exists() else None
    if code is None:
        return web.json_response({"supported": False})
    return web.json_response({"supported": True, "code": code, "current": sandbox.full(code), **sandbox.catalog()})


async def h_sandbox_set(request):
    i = inst_of(request)
    if get_prop(i.cfg, "SandboxCode", None) is None:
        raise web.HTTPConflict(text="This game version has no Sandbox Options (V3+ only)")
    d = await request.json()
    if "code" in d:
        code = str(d["code"]).strip()
        if not re.fullmatch(r"A([A-Z]{3})*", code):
            raise web.HTTPBadRequest(text="Invalid SandboxCode")
    else:
        cur = sandbox.full(get_prop(i.cfg, "SandboxCode"))
        for k, idx in (d.get("values") or {}).items():
            if k not in sandbox.OPTIONS or not 0 <= int(idx) < len(sandbox.values(k)):
                raise web.HTTPBadRequest(text=f"Invalid value for {k}")
            cur[k] = int(idx)
        code = sandbox.encode(cur)
    write_config_props(i.cfg, {"SandboxCode": code})
    i.note(f"Sandbox options saved ({code}) - applies after restart")
    i.push_state()
    return ok(code=code)


# ------------------------------------------------------------------ config export / import
EXPORTS = DATA / "exports"
KEEP_ON_IMPORT = ("ServerName", "GameName", "ServerPort", "TelnetPort", "WebDashboardPort", "UserDataFolder", "TelnetEnabled")
PANEL_KEYS_SKIP = ("game_version",)


def build_export(i) -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("7edcore-export.json", json.dumps({"format": 1, "server": i.name, "game": i.game_version_label(),
                                                      "branch": i.branch, "exported": int(__import__("time").time())}, indent=2))
        if i.cfg.exists():
            z.write(i.cfg, "serverconfig.xml")
        z.writestr("panel-settings.json", json.dumps(i.settings, indent=2, ensure_ascii=False))
        adm = i.userdata / "Saves" / (get_prop(i.cfg, "AdminFileName") or "serveradmin.xml")
        if adm.exists():
            z.write(adm, "serveradmin.xml")
        if (i.dir / "mods.json").exists():
            z.write(i.dir / "mods.json", "mods.json")
    return buf.getvalue()


async def h_export(request):
    i = inst_of(request)
    data = await asyncio.to_thread(build_export, i)
    from .util import slugify, stamp
    name = f"7edcore_{slugify(i.name)}_{stamp()}.zip"
    if request.method == "POST":                       # keep a copy on the server
        EXPORTS.mkdir(parents=True, exist_ok=True)
        (EXPORTS / name).write_bytes(data)
        i.note(f"Configuration exported to /exports/{name}")
        return ok(path=f"/exports/{name}")
    return web.Response(body=data, content_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


async def h_exports(request):
    EXPORTS.mkdir(parents=True, exist_ok=True)
    files = [{"path": f"/exports/{f.name}", "name": f.name, "size": f.stat().st_size, "mtime": f.stat().st_mtime}
             for f in sorted(EXPORTS.glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)]
    return web.json_response({"exports": files, "servers": [{"id": x.id, "name": x.name} for x in HUB.instances.values()]})


def apply_import(i, src: dict, parts):
    """src: {"serverconfig.xml": bytes, "panel-settings.json": bytes, "serveradmin.xml": bytes}"""
    done = []
    if "game" in parts and src.get("serverconfig.xml"):
        if not i.cfg.exists():
            raise web.HTTPConflict(text="Install the game version first")
        tmp = i.cfg.with_suffix(".import.xml")
        tmp.write_bytes(src["serverconfig.xml"])
        try:
            ET.parse(tmp)
        except ET.ParseError as e:
            tmp.unlink()
            raise web.HTTPBadRequest(text=f"serverconfig.xml is not valid XML: {e}")
        new = {n: v for n, v, _ in read_config_props(tmp)}
        tmp.unlink()
        for k in KEEP_ON_IMPORT:
            new.pop(k, None)
        shutil.copy2(i.cfg, i.cfg.with_suffix(".xml.bak"))
        write_config_props(i.cfg, new)
        done.append(f"game settings ({len(new)})")
    if "panel" in parts and src.get("panel-settings.json"):
        d = json.loads(src["panel-settings.json"])
        for k, v in d.items():
            if k in DEFAULT_SETTINGS and k not in PANEL_KEYS_SKIP:
                i.settings[k] = validate_schedule(v) if k == "schedule" else v
        i.save_settings()
        done.append("panel settings")
    if "admins" in parts and src.get("serveradmin.xml"):
        try:
            ET.fromstring(src["serveradmin.xml"])
        except ET.ParseError as e:
            raise web.HTTPBadRequest(text=f"serveradmin.xml is not valid XML: {e}")
        dest = i.userdata / "Saves" / (get_prop(i.cfg, "AdminFileName") or "serveradmin.xml")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.copy2(dest, dest.with_name(dest.name + ".bak"))
        dest.write_bytes(src["serveradmin.xml"])
        done.append("admins")
    if not done:
        raise web.HTTPBadRequest(text="Nothing to import - the file has none of the selected parts")
    i.note("Configuration imported: " + ", ".join(done) + " - applies after restart")
    i.push_state()
    return done


def read_bundle(path: Path):
    if zipfile.is_zipfile(path):
        out = {}
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                base = Path(n).name
                if base in ("serverconfig.xml", "panel-settings.json", "serveradmin.xml") and z.getinfo(n).file_size < 5 << 20:
                    out[base] = z.read(n)
        return out
    raw = path.read_bytes()[:5 << 20]
    if b"<ServerSettings" in raw:
        return {"serverconfig.xml": raw}
    if b"<adminTools" in raw:
        return {"serveradmin.xml": raw}
    raise web.HTTPBadRequest(text="Expected a 7edCore export ZIP, serverconfig.xml or serveradmin.xml")


async def h_import_config(request):
    i = inst_of(request)
    if request.content_type.startswith("multipart/"):
        tmp = Path(tempfile.mkdtemp(dir=i.dir, prefix=".up_"))
        try:
            files, fields = await read_upload(request, tmp, exts=(".zip", ".xml"))
            if not files:
                raise web.HTTPBadRequest(text="Choose a file")
            src = read_bundle(files[0])
            parts = fields.get("parts", "game,panel,admins").split(",")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        d = await request.json()
        parts = d.get("parts") or ["game", "panel", "admins"]
        if d.get("from_server"):
            o = HUB.get(d["from_server"])
            src = {}
            if o.cfg.exists():
                src["serverconfig.xml"] = o.cfg.read_bytes()
            src["panel-settings.json"] = json.dumps(o.settings).encode()
            adm = o.userdata / "Saves" / (get_prop(o.cfg, "AdminFileName") or "serveradmin.xml")
            if adm.exists():
                src["serveradmin.xml"] = adm.read_bytes()
        elif d.get("path"):
            src = read_bundle(safe_path(d["path"]))
        else:
            raise web.HTTPBadRequest(text="Choose a source")
    return ok(imported=apply_import(i, src, parts))


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


# ------------------------------------------------------------------ local API (7edcore command line, power/UPS hooks)
POWER_FILE = PANEL_DIR / "power.json"


async def h_local_status(request):
    return web.json_response({"version": __import__("sevenedcore").__version__, "servers": [
        {"id": i.id, "name": i.name, "state": i.state, "players": len(i.players), "game": i.game_version_label(),
         "branch": i.branch, "port": get_prop(i.cfg, "ServerPort"), "pending": i.pending_what}
        for i in (HUB.instances[x] for x in HUB.order)],
        "power_stopped": load_json(POWER_FILE, {}).get("stopped", [])})


async def h_local_save(request):
    saved = []
    for i in HUB.instances.values():
        if i.state == "running" and i.tw:
            try:
                await i.command("saveworld", timeout=30)
                i.note("World saved (7edcore save)")
                saved.append(i.id)
            except web.HTTPException as e:
                i.note(f"Save failed: {e.text}")
    return ok(saved=saved)


async def h_local_stop_all(request):
    reason = (await request.json() if request.can_read_body else {}).get("reason") or "7edcore stop-all"
    running = [i for i in HUB.instances.values() if i.running()]
    prev = load_json(POWER_FILE, {}).get("stopped", [])
    save_json(POWER_FILE, {"stopped": sorted(set(prev) | {i.id for i in running}), "reason": reason})
    for i in running:
        await i.say("Server is shutting down (power), saving the world...", "FF4444")
    await asyncio.gather(*(i.stop(user=False, reason=reason) for i in running), return_exceptions=True)
    return ok(stopped=[i.id for i in running])


async def h_local_resume(request):
    ids = load_json(POWER_FILE, {}).get("stopped", [])
    started, failed = [], {}
    for iid in ids:
        i = HUB.instances.get(iid)
        if not i or i.running():
            continue
        try:
            await i.start(reason="resume")
            started.append(iid)
        except CompatError as e:
            failed[iid] = e.message
        except web.HTTPException as e:
            failed[iid] = e.text
    save_json(POWER_FILE, {"stopped": list(failed)})
    return ok(started=started, failed=failed)


async def h_local_server(request):
    i = inst_of(request)
    act = request.match_info["act"]
    if act == "start":
        await i.start(reason="7edcore command")
    elif act == "stop":
        await i.stop(user=True, reason="7edcore command")
    elif act == "restart":
        await i.restart(reason="7edcore command")
    else:
        raise web.HTTPNotFound()
    return ok(state=i.state)


async def h_local_update(request):
    selfupdate.request()
    return ok()


def routes(app):
    r0 = app.router
    r0.add_get("/api/local/status", h_local_status)
    r0.add_post("/api/local/save", h_local_save)
    r0.add_post("/api/local/stop-all", h_local_stop_all)
    r0.add_post("/api/local/resume", h_local_resume)
    r0.add_post("/api/local/request-update", h_local_update)
    r0.add_post("/api/local/s/{iid}/{act}", h_local_server)
    r = app.router
    r.add_get("/api/overview", h_overview)
    r.add_get("/api/presets", h_presets)
    r.add_get("/api/configmeta", h_configmeta)
    r.add_get("/api/global", h_global_get)
    r.add_post("/api/global", h_global_set)
    r.add_post("/api/selfupdate", h_selfupdate)
    r.add_post("/api/selfupdate/now", h_selfupdate_now)
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
    r.add_post(p + "/quick/{act}", h_quick)
    r.add_get(p + "/compat", h_compat)
    r.add_post(p + "/command", h_command)
    r.add_get(p + "/players", h_players)
    r.add_get(p + "/settings", h_settings_get)
    r.add_post(p + "/settings", h_settings_set)
    r.add_get(p + "/config", h_config_get)
    r.add_post(p + "/config", h_config_set)
    r.add_post(p + "/preset", h_preset_apply)
    r.add_post(p + "/preset/preview", h_preset_preview)
    r.add_get(p + "/sandbox", h_sandbox_get)
    r.add_post(p + "/sandbox", h_sandbox_set)
    r.add_get(p + "/export", h_export)
    r.add_post(p + "/export", h_export)
    r.add_post(p + "/import-config", h_import_config)
    r.add_get("/api/exports", h_exports)
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
