"""Game auto-update policy test. Panel must run with FAKE_PUBLIC_BUILD=2002 on data from api_test."""
import asyncio, sys, time, aiohttp
URL, PW = sys.argv[1], sys.argv[2]
async def main():
    async with aiohttp.ClientSession(headers={"X-Requested-With": "7edcore"}, cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        async def j(m, p, **kw):
            async with s.request(m, URL + p, **kw) as r:
                return r.status, await r.json()
        await j("POST", "/api/login", json={"password": PW})
        st, d = await j("POST", "/api/s/server-1/settings", json={"game_updates": "notify"})
        st, d = await j("POST", "/api/updates/check")
        n = d["notices"]["server-1"].get("game_update")
        print("notify:", n)
        assert n and n["available"] and n["kind"] == "minor" and n["target"] == "V 3.4.1", n
        st, d = await j("GET", "/api/versions")
        assert next(b for b in d["branches"] if b["name"] == "public")["installed_build"] == "2001"
        st, d = await j("POST", "/api/s/server-1/settings", json={"game_updates": "minor", "update_window": "stopped"})
        st, d = await j("POST", "/api/updates/check")
        st, d = await j("GET", "/api/versions")
        pub = next(b for b in d["branches"] if b["name"] == "public")
        print("after auto:", pub["installed_build"], pub["version"])
        assert pub["installed_build"] == "2002"
        st, d = await j("GET", "/api/s/server-1/backups")
        kinds = [b["kind"] for b in d["backups"]]
        print("backups:", kinds)
        assert "pre-update" in kinds
        st, d = await j("GET", "/api/s/server-1/status")
        print("compat after update:", d["compat"], d["game"]["version"])
        print("OK")
asyncio.run(main())
