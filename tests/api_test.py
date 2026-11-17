"""End-to-end API test against fake steamcmd + fake server. Usage: python3 api_test.py http://127.0.0.1:18200 pass"""
import asyncio, io, json, sys, time, zipfile
import aiohttp

URL, PW = sys.argv[1], sys.argv[2]
H = {"X-Requested-With": "7edcore"}
fails = 0


def check(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails += 1


async def main():
    async with aiohttp.ClientSession(headers=H, cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        async def j(method, path, **kw):
            async with s.request(method, URL + path, **kw) as r:
                try:
                    return r.status, await r.json()
                except Exception:
                    return r.status, await r.text()

        async def wait(pred, path, t=30):
            end = time.time() + t
            while time.time() < end:
                st, d = await j("GET", path)
                if pred(d):
                    return d
                await asyncio.sleep(0.5)
            return d

        async with aiohttp.ClientSession() as raw:
            async with raw.post(URL + "/api/login", json={"password": PW}) as r:
                check(r.status == 403, f"CSRF header required ({r.status})")
        st, d = await j("GET", "/api/overview")
        check(st == 401, "overview needs login")
        st, d = await j("POST", "/api/login", json={"password": "wrong"})
        check(st == 401, "wrong password rejected")
        st, d = await j("POST", "/api/login", json={"password": PW})
        check(st == 200, f"login {d}")
        st, d = await j("GET", "/api/versions")
        names = [b["name"] for b in d["branches"]]
        check("alpha21.2" in names and "public" in names, f"branches listed: {names}")
        pub = next(b for b in d["branches"] if b["name"] == "public")
        check(pub["version"] == "V 3.4", f"public resolves to V 3.4.0 via build: {pub['version']}")
        st, d = await j("GET", "/api/configmeta")
        check(st == 200 and "GameDifficulty" in d["props"], "config metadata")
        st, ov = await j("GET", "/api/overview")
        iid = ov["instances"][0]["id"]
        P = f"/api/s/{iid}"
        st, d = await j("POST", "/api/versions/public/install")
        check(st == 200, "install started")
        await wait(lambda d: d["busy"] is None and not d["queued"] and any(b["name"] == "public" and b["installed"] for b in d["branches"]), "/api/versions")
        st, d = await j("GET", P + "/config")
        check(d["exists"], "config created after install")
        st, d = await j("POST", P + "/preset/preview", json={"tier": "hard", "seed": 42})
        check(st == 200 and d["sandbox"] and len(d["preset"]["twists"]) >= 3, f"random preview {d.get('preset', {}).get('desc')}")
        st, d = await j("POST", P + "/preset", json={"id": "lootbag_only"})
        check(st == 200 and d["sandbox"] and "SandboxCode" in d["changes"] and d["modlets"] == ["empty_world_loot", "more_loot_bags"], f"lootbag preset {d.get('diff')}")
        st, sb = await j("GET", P + "/sandbox")
        check(sb["supported"] and sb["current"]["HarvestingOutput"] == 0 and sb["current"]["RangedDamage"] == 9, "sandbox code written, other options kept")
        st, d = await j("GET", P + "/mods")
        check(any(m["folder"] == "7edCore-Challenge" for m in d["mods"]), "challenge modlet installed")
        st, d = await j("POST", P + "/preset", json={"id": "standard"})
        st, sb = await j("GET", P + "/sandbox")
        st, md = await j("GET", P + "/mods")
        check(sb["current"]["HarvestingOutput"] == 7 and not any(m["folder"] == "7edCore-Challenge" for m in md["mods"]), "standard resets preset options and removes modlet")
        st, d = await j("POST", P + "/preset", json={"stack": [{"id": "weekend"}, {"id": "short_fuse"}, {"tier": "hard", "seed": 7}]})
        st, sb = await j("GET", P + "/sandbox")
        check(st == 200 and sb["current"]["DayNightLength"] == 6 and any(o["key"] == "DayNightLength" for o in d["overridden"]), "stack: top preset wins")
        st, d = await j("POST", P + "/preset", json={"stack": [{"id": "short_fuse"}, {"id": "weekend"}]})
        st, sb = await j("GET", P + "/sandbox")
        st, ss = await j("GET", P + "/status")
        check(sb["current"]["DayNightLength"] == 3 and [x["id"] for x in ss["preset_stack"]] == ["short_fuse", "weekend"], "stack: reorder changes winner, stack saved")
        st, d = await j("POST", P + "/preset", json={"id": "standard"})
        st, d = await j("POST", P + "/preset", json={"stack": [{"id": "z_extreme"}, {"id": "diff_insane"}]})
        st, sb = await j("GET", P + "/sandbox")
        c = sb["current"]
        check(sb["code"].startswith("AAAD") and c["EntityIncomingDamage"] == 1 and c["IncomingDamage"] == 11, f"insane + extreme zombies {sb['code']}")
        st, d = await j("POST", P + "/preset", json={"id": "o_biteclub"})
        st, sb = await j("GET", P + "/sandbox")
        want = "AAAGABGACGADGARJAHJBADBDGBIBBMCBNEBPFBZFCFDCXADADEYA"
        check(sorted(sb["code"][1 + k:4 + k] for k in range(0, len(sb["code"]) - 1, 3)) == sorted(want[1 + k:4 + k] for k in range(0, len(want) - 1, 3)),
              f"official preset reproduces the game code: {sb['code']}")
        st, d = await j("POST", P + "/preset", json={"id": "standard"})
        st, d = await j("POST", P + "/sandbox", json={"values": {"XPMultiplier": 6}})
        st, sb = await j("GET", P + "/sandbox")
        check(sb["current"]["XPMultiplier"] == 6 and "AS" in sb["code"], f"sandbox option set {sb['code']}")
        st, d = await j("POST", P + "/config", json={"changes": {"ServerMaxPlayerCount": "6", "UserDataFolder": "/evil"}})
        st, d = await j("GET", P + "/config")
        props = {p["name"]: p["value"] for p in d["props"]}
        check(props["ServerMaxPlayerCount"] == "6" and props["UserDataFolder"].startswith("/tmp"), "config set, managed key protected")
        st, d = await j("POST", P + "/settings", json={"ram_limit_gb": 6, "game_updates": "minor", "bogus": 1})
        check(st == 200 and d["settings"]["ram_limit_gb"] == 6.0, "settings saved")
        st, d = await j("POST", P + "/settings", json={"game_updates": "major"})
        check(st == 400, "invalid policy rejected")
        st, d = await j("POST", P + "/server/start")
        check(st == 200, f"start {d}")
        d = await wait(lambda d: d["state"] == "running", P + "/status")
        check(d["state"] == "running", "server running")
        await asyncio.sleep(2)
        st, d = await j("GET", P + "/status")
        check(d["game"]["version"] == "V 3.4", f"version learned {d['game']['version']}")
        st, d = await j("POST", P + "/command", json={"command": "version"})
        check("V 3.4.0" in "\n".join(d["output"]), f"command output {d['output']}")
        st, d = await j("POST", P + "/server/stop")
        d = await wait(lambda d: d["state"] == "stopped", P + "/status", 40)
        check(d["state"] == "stopped", "stopped")
        check(d["compat"]["level"] == "same" and d["compat"]["save_version"] == "V 3.4", f"save version tracked {d['compat']}")
        st, d = await j("POST", P + "/version", json={"branch": "v2.6"})
        check(st == 409 and d["compat"]["level"] == "downgrade", f"downgrade warning {st} {d}")
        st, d = await j("GET", P + "/compat?branch=v3.3.0")
        check(d["level"] == "downgrade", f"compat preview older minor {d['level']}")
        st, d = await j("GET", P + "/compat?branch=alpha21.2")
        check(d["level"] in ("downgrade", "major"), f"compat preview alpha {d['level']}")
        st, d = await j("POST", "/api/servers", json={"name": "Alpha Fun", "game_version": "alpha21.2"})
        check(st == 200, f"create server 2 {d}")
        iid2 = d["id"]
        await wait(lambda d: d["busy"] is None and not d["queued"] and any(b["name"] == "alpha21.2" and b["installed"] for b in d["branches"]), "/api/versions")
        st, d = await j("GET", f"/api/s/{iid2}/status")
        check(d["world"]["ServerPort"] == "36910" and d["game"]["version"] == "Alpha 21.2", f"server 2 port/version {d['world']['ServerPort']} {d['game']['version']}")
        st, d = await j("POST", f"/api/s/{iid2}/preset", json={"id": "black_market"})
        check(st == 200 and not d["sandbox"] and d["modlets"] == ["trader_prices_legacy"], f"legacy preset + legacy modlet {d.get('modlets')}")
        st, d = await j("POST", f"/api/s/{iid2}/preset", json={"id": "horde_week"})
        check(st == 200 and d["changes"].get("BloodMoonFrequency") == "3" and d["changes"].get("GameDifficulty") == "2", f"legacy preset props {d.get('changes')}")
        # import world
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("MyOldSave/Navezgane/OldGame/main.ttw", "x")
            z.writestr("MyOldSave/Navezgane/OldGame/players.xml", "<x/>")
        fd = aiohttp.FormData()
        fd.add_field("file", buf.getvalue(), filename="old.zip")
        fd.add_field("version", "V 3.3")
        st, d = await j("POST", f"/api/s/{iid2}/worlds/import", data=fd)
        check(st == 200, f"import world {d}")
        st, d = await j("GET", f"/api/s/{iid2}/status")
        check(d["compat"]["level"] in ("downgrade", "major") and d["compat"]["save_version"] == "V 3.3", f"imported save compat {d['compat']}")
        st, d = await j("POST", f"/api/s/{iid2}/server/start")
        check(st == 409 and "compat" in d, f"start blocked by compat {st}")
        # mods
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("CoolMod/ModInfo.xml", '<xml><Name value="CoolMod"/><Version value="1.2"/><Description value="For V 3.4"/></xml>')
            z.writestr("CoolMod/Config/items.xml", "<configs/>")
        fd = aiohttp.FormData()
        fd.add_field("file", buf.getvalue(), filename="coolmod.zip")
        st, d = await j("POST", P + "/mods/upload", data=fd)
        check(st == 200, f"mod upload {d}")
        st, d = await j("GET", P + "/mods")
        check(any(m["folder"] == "CoolMod" for m in d["mods"]), f"mod listed {[m['folder'] for m in d['mods']]}")
        st, d = await j("POST", P + "/mods/CoolMod/toggle")
        check(d.get("enabled") is False, "mod disabled")
        st, d = await j("POST", P + "/mods/CoolMod/source", json={"source": "github.com/someone/coolmod"})
        check(st == 200, "mod source set")

        def modzip(name, extra=None):
            b = io.BytesIO()
            with zipfile.ZipFile(b, "w") as z:
                z.writestr(f"{name}/ModInfo.xml", f'<xml><Name value="{name}"/><Version value="1.0"/></xml>')
                for k, v in (extra or {}).items():
                    z.writestr(f"{name}/{k}", v)
            return b.getvalue()
        # batch upload: all files arrive, all install
        fd = aiohttp.FormData()
        fd.add_field("file", modzip("ModA", {"Config/items.xml": "<configs/>", "Settings.xml": "<s><opt v='1'/></s>"}), filename="moda.zip")
        fd.add_field("file", modzip("ModB", {"config.json": '{"speed": 1}', "ReadMe.txt": "hi"}), filename="modb.zip")
        st, d = await j("POST", P + "/mods/upload", data=fd)
        check(st == 200 and sorted(r["folder"] for r in d["report"]) == ["ModA", "ModB"], f"batch upload {d}")
        # a broken file in the batch -> nothing from the batch is installed
        fd = aiohttp.FormData()
        fd.add_field("file", modzip("ModC"), filename="modc.zip")
        fd.add_field("file", modzip("ModD")[:-30], filename="modd.zip")
        st, d = await j("POST", P + "/mods/upload", data=fd)
        st2, ml = await j("GET", P + "/mods")
        names = [m["folder"] for m in ml["mods"]]
        check(st == 400 and "ModC" not in names and "ModD" not in names, f"broken batch rejected, nothing installed {st} {names}")
        check(ml["total"]["count"] == 3 and ml["total"]["size"] > 0 and ml["total"]["enabled"] == 2, f"mod totals {ml['total']}")
        # cancelled upload: client disconnects mid-body -> no temp files, nothing installed
        from urllib.parse import urlparse
        u = urlparse(URL)
        cookie = "; ".join(f"{c.key}={c.value}" for c in s.cookie_jar)
        body = (b"--XyZ\r\nContent-Disposition: form-data; name=\"file\"; filename=\"half.zip\"\r\n"
                b"Content-Type: application/zip\r\n\r\n" + modzip("HalfMod", {"big.bin": "x" * 200000})[:50000])
        rd, wr = await asyncio.open_connection(u.hostname, u.port)
        wr.write((f"POST {P}/mods/upload HTTP/1.1\r\nHost: {u.hostname}\r\nX-Requested-With: 7edcore\r\nCookie: {cookie}\r\n"
                  f"Content-Type: multipart/form-data; boundary=XyZ\r\nContent-Length: 900000\r\n\r\n").encode() + body)
        await wr.drain()
        await asyncio.sleep(0.5)
        wr.close()
        await asyncio.sleep(1)
        st2, ml = await j("GET", P + "/mods")
        check("HalfMod" not in [m["folder"] for m in ml["mods"]], "aborted upload installs nothing")
        st, junk = await j("GET", f"/api/files?path=/instances/{iid}")
        check(not any(x["name"].startswith(".up_") for x in junk["items"]), "no leftover upload temp dirs")
        # mod config files
        st, d = await j("GET", P + "/mods/ModA/files")
        paths = {f["path"]: f["kind"] for f in d["files"]}
        check(paths.get("Settings.xml") == "settings" and paths.get("Config/items.xml") == "patch" and "ModInfo.xml" not in paths,
              f"mod config files {paths}")
        st, d = await j("GET", P + "/mods/ModB/files")
        check([f["path"] for f in d["files"]] == ["config.json"], f"readme skipped {d['files']}")
        st, d = await j("GET", P + "/mods/ModA/file?path=Settings.xml")
        check(st == 200 and "opt" in d["content"], "read mod config")
        st, d = await j("POST", P + "/mods/ModA/file", json={"path": "Settings.xml", "content": "<s><opt v='2'></s>"})
        check(st == 400, "invalid XML not saved")
        st, d = await j("POST", P + "/mods/ModA/file", json={"path": "Settings.xml", "content": "<s><opt v='2'/></s>"})
        check(st == 200 and any(f["path"] == "Settings.xml" and f["edited"] and f["has_original"] for f in d["files"]), f"mod config saved {d}")
        st, d = await j("GET", P + "/mods/ModA/file?path=../../serverconfig.xml")
        check(st == 404, "path escape blocked")
        st, d = await j("POST", P + "/mods/ModB/file", json={"path": "config.json", "content": '{"speed": 2}'})
        st, d = await j("POST", P + "/mods/ModB/file", json={"path": "config.json", "reset": True})
        st, d = await j("GET", P + "/mods/ModB/file?path=config.json")
        check('"speed": 1' in d["content"], "reset to original")
        # web map + dynamic day length (server 1 running)
        st, d = await j("POST", P + "/webmap", json={"enabled": True, "public": True})
        check(st == 200 and d["enabled"] and d["rendering"] and d["permission"] == 2000, f"web map enabled + public {d}")
        st, d = await j("POST", P + "/settings", json={"daylen_dynamic": True, "daylen_ref": 2, "daylen_above": 50,
                                                        "daylen_below": -50, "daylen_freeze": True, "daylen_base": 60})
        check(st == 200, "day length settings")
        st, d = await j("POST", P + "/settings", json={"daylen_below": -95})
        check(st == 400, "day length limits")
        st, d = await j("POST", P + "/server/start")
        d = await wait(lambda d: d["state"] == "running" and d["console_connected"], P + "/status")
        st, d = await j("GET", P + "/webmap")
        check(d.get("reachable") is True, f"web map reachable {d}")
        st, d = await j("POST", P + "/quick/fps")
        check(st == 200 and d["meminfo"].get("fps") == "30.00", f"FPS on request {d}")
        d = await wait(lambda d: d["daylen"]["frozen"], P + "/status", 40)
        check(d["daylen"]["frozen"], f"time frozen with 0 players {d['daylen']}")
        st, cfgd = await j("GET", P + "/config")
        udir = next(p["value"] for p in cfgd["props"] if p["name"] == "UserDataFolder") if isinstance(cfgd.get("props"), list) else cfgd["props"]["UserDataFolder"]
        open(udir + "/fake_players", "w").write("4")
        d = await wait(lambda d: d["daylen"]["applied"] == 30, P + "/status", 40)
        check(not d["daylen"]["frozen"] and d["daylen"]["applied"] == 30, f"4 players, ref 2, +50%/player -> 30 min days {d['daylen']}")
        open(udir + "/fake_players", "w").write("1")
        d = await wait(lambda d: d["daylen"]["applied"] == 120, P + "/status", 40)
        check(d["daylen"]["applied"] == 120, f"1 player, -50% -> 120 min days {d['daylen']}")
        import os as _os
        _os.remove(udir + "/fake_players")
        st, d = await j("POST", P + "/settings", json={"daylen_dynamic": False})
        st, d = await j("POST", P + "/server/stop")
        await wait(lambda d: d["state"] == "stopped", P + "/status", 40)
        # backups
        st, d = await j("POST", P + "/backups/create")
        await wait(lambda d: len(d["backups"]) > 0 and not d["busy"], P + "/backups")
        st, d = await j("GET", P + "/backups")
        check(len(d["backups"]) >= 1, f"backup created {[b['name'] for b in d['backups']]}")
        st, d = await j("GET", "/api/files?path=/instances")
        check(st == 200 and len(d["items"]) == 2, "files list")
        st, d = await j("POST", "/api/files/delete", json={"path": "/instances/" + iid})
        check(st == 403, "protected folder")
        st, d = await j("GET", P + "/worlds")
        check(st == 200 and "Navezgane" in d["builtin"], f"worlds {d.get('builtin')}")
        # ---- users and roles
        st, d = await j("GET", "/api/session")
        check(d["user"]["name"] == "admin" and d["user"]["role"] == "admin", f"session user {d.get('user')}")
        st, d = await j("POST", "/api/users", json={"username": "op1", "password": "operator-pass", "role": "operator", "servers": [iid2]})
        check(st == 200, f"create operator {d}")
        st, d = await j("POST", "/api/users", json={"username": "view1", "password": "short", "role": "viewer"})
        check(st == 400, "password rules")
        st, d = await j("POST", "/api/users", json={"username": "view1", "password": "viewer-pass", "role": "viewer"})
        async with aiohttp.ClientSession(headers=H, cookie_jar=aiohttp.CookieJar(unsafe=True)) as o:
            async def oj(method, path, **kw):
                async with o.request(method, URL + path, **kw) as r:
                    try:
                        return r.status, await r.json()
                    except Exception:
                        return r.status, None
            st, d = await oj("POST", "/api/login", json={"username": "op1", "password": "wrong-pass"})
            check(st == 401, "operator wrong password")
            st, d = await oj("POST", "/api/login", json={"username": "op1", "password": "operator-pass"})
            st, d = await oj("GET", "/api/overview")
            check([x["id"] for x in d["instances"]] == [iid2], f"operator sees only own server {[x['id'] for x in d['instances']]}")
            st, d = await oj("GET", P + "/status")
            check(st == 403, "operator blocked from other server")
            st, d = await oj("POST", f"/api/s/{iid2}/settings", json={"ram_limit_gb": 1})
            check(st == 403, "operator cannot change settings")
            st, d = await oj("GET", "/api/files?path=/")
            check(st == 403, "operator cannot browse files")
            st, d = await oj("POST", f"/api/s/{iid2}/quick/check")
            check(st == 200, "operator can use quick actions")
            st, d = await oj("GET", f"/api/s/{iid2}/config")
            check(st == 403, "operator cannot read config (passwords)")
        async with aiohttp.ClientSession(headers=H, cookie_jar=aiohttp.CookieJar(unsafe=True)) as v:
            async with v.post(URL + "/api/login", json={"username": "view1", "password": "viewer-pass"}) as r:
                pass
            async with v.post(URL + f"/api/s/{iid2}/server/start") as r:
                check(r.status == 403, "viewer cannot start")
            async with v.get(URL + f"/api/s/{iid2}/status") as r:
                check(r.status == 200, "viewer can watch")
        st, d = await j("POST", "/api/users/admin", json={"role": "viewer"})
        check(st == 409, "last admin cannot be demoted")
        st, d = await j("POST", "/api/users/view1/delete")
        check(st == 200, "delete user")
        # clone = 1:1 replica on a chosen port
        st, ov = await j("GET", "/api/overview")
        check(ov["free_ports"] == [36920, 36930], f"free ports {ov['free_ports']}")
        st, d = await j("POST", "/api/servers", json={"name": "Clone", "clone_from": iid, "port": 36910})
        check(st == 409, "used port rejected")
        st, d = await j("POST", "/api/servers", json={"name": "Clone", "clone_from": iid, "port": 36930})
        check(st == 200, f"clone created {d}")
        iid3 = d["id"]
        d = await wait(lambda d: not d["busy"], f"/api/s/{iid3}/status")
        check(d["world"]["ServerPort"] == "36930", f"clone port {d['world']['ServerPort']}")
        sts = [(await j("GET", f"/api/s/{x}/status"))[1]["ports"] for x in (iid, iid2, iid3)]
        check(len({p["telnet"] for p in sts}) == 3 and len({p["web"] for p in sts}) == 3, f"telnet / web ports unique {sts}")
        st, d = await j("GET", f"/api/s/{iid3}/mods")
        check(sorted(m["folder"] for m in d["mods"]) == ["CoolMod", "ModA", "ModB"], f"clone mods {[m['folder'] for m in d['mods']]}")
        st, d = await j("GET", f"/api/s/{iid3}/mods/ModA/file?path=Settings.xml")
        check("v='2'" in d.get("content", ""), "clone keeps edited mod config")
        st, d = await j("GET", f"/api/s/{iid3}/mods/ModA/files")
        check(any(f["path"] == "Settings.xml" and f["edited"] for f in d["files"]), "clone keeps mod metadata (edited flag)")
        st, d = await j("GET", f"/api/s/{iid3}/settings")
        check(d.get("ram_limit_gb") == 6.0 and d.get("webmap_public") is True, "clone keeps panel settings")
        st, d = await j("GET", f"/api/files?path=/instances/{iid3}/userdata/Saves")
        check(st == 200 and any(x["name"] == "serveradmin.xml" for x in d["items"]) and any(x["dir"] for x in d["items"]),
              f"clone keeps saves + admins {[x['name'] for x in d.get('items', [])]}")
        st, d = await j("GET", f"/api/s/{iid3}/webmap")
        check(d["port"] == "38083" and d["permission"] == 2000, f"clone web map port + permission {d}")
        st, d = await j("POST", f"/api/s/{iid3}/delete", json={"confirm": "Clone"})
        check(st == 200, "delete clone")
        st, d = await j("POST", f"/api/s/{iid2}/delete", json={"confirm": "Alpha Fun"})
        check(st == 200, "delete server 2")
    print(f"\n{fails} failures")
    sys.exit(1 if fails else 0)

asyncio.run(main())
