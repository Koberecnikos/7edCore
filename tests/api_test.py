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
        st, d = await j("POST", f"/api/s/{iid2}/delete", json={"confirm": "Alpha Fun"})
        check(st == 200, "delete server 2")
    print(f"\n{fails} failures")
    sys.exit(1 if fails else 0)

asyncio.run(main())
