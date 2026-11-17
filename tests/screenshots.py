"""Build a demo panel state (fake game server) and take the README screenshots.
Usage: python3 screenshots.py http://127.0.0.1:18200 pass <datadir> <outdir>"""
import asyncio, io, os, sys, zipfile
import aiohttp
from playwright.async_api import async_playwright

URL, PW, DATA, OUT = sys.argv[1:5]
H = {"X-Requested-With": "7edcore"}


def modzip(name, ver, desc, author, files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(f"{name}/ModInfo.xml", f'<xml><DisplayName value="{name.replace("_", " ")}"/><Name value="{name}"/><Version value="{ver}"/>'
                                          f'<Description value="{desc}"/><Author value="{author}"/></xml>')
        for k, v in files.items():
            z.writestr(f"{name}/{k}", v)
    return b.getvalue()


MODS = [
    ("BetterBackpacks", "2.1.0", "Bigger backpack and vehicle storage.", "kraken", {"Config/XUi/windows.xml": "<configs/>", "Config/items.xml": "<configs/>"}),
    ("ServerTools_Lite", "1.4.2", "Chat commands, MOTD, auto-messages and vote rewards for dedicated servers.", "obsidian",
     {"ServerToolsConfig.xml": '<?xml version="1.0"?>\n<ServerTools>\n  <Motd enabled="true" message="Welcome to the wasteland!" />\n'
      '  <AutoMessages enabled="true" delayMinutes="20">\n    <Message text="Blood moon every 7 days - build a base!" />\n'
      '    <Message text="Type /help for commands" />\n  </AutoMessages>\n  <Vote enabled="false" reward="casinoCoin" count="250" />\n</ServerTools>\n',
      "Config/Localization.txt": "Key,English\n"}),
    ("NoBuffHud", "1.0", "Hides buff icons from the HUD.", "minimal", {"Config/XUi/windows.xml": "<configs/>"}),
    ("SmarterZombies", "3.0.1", "Zombies flank, climb and remember where they lost you.", "undead-lab",
     {"settings.json": '{\n  "flanking": true,\n  "climbChance": 0.25,\n  "memorySeconds": 45\n}\n', "Config/entityclasses.xml": "<configs/>"}),
    ("Bigger_Hordes", "1.2", "Blood moon hordes scale with the number of players.", "hordemaster", {"Config/gamestages.xml": "<configs/>"}),
    ("StorageMadness", "1.0.7", "Craft from nearby containers, quick stack, shared storage.", "oldmodder",
     {"StorageMadness.dll": open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake", "game", "TestCodeMod.dll"), "rb").read(),
      "FAKE_BROKEN": "", "Config/items.xml": "<configs><remove xpath=\"/items/item[@name='oldBackpack']\"/></configs>"}),
    ("QuickLoot", "2.0", "Loot all / quick stack buttons in containers.", "lazyhands", {"FAKE_PARTIAL": "", "Config/XUi/windows.xml": "<configs/>"}),
]


async def setup():
    async with aiohttp.ClientSession(headers=H, cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        async def j(m, p, **kw):
            async with s.request(m, URL + p, **kw) as r:
                try:
                    return await r.json()
                except Exception:
                    return await r.text()
        await j("POST", "/api/login", json={"password": PW})
        await j("POST", "/api/versions/public/install")
        for _ in range(60):
            v = await j("GET", "/api/versions")
            if any(b["name"] == "public" and b["installed"] for b in v["branches"]) and not v["busy"]:
                break
            await asyncio.sleep(0.5)
        ov = await j("GET", "/api/overview")
        iid = ov["instances"][0]["id"]
        await j("POST", f"/api/s/{iid}/rename", json={"name": "Wasteland PvE"})
        P = f"/api/s/{iid}"
        fd = aiohttp.FormData()
        for m in MODS:
            fd.add_field("file", modzip(*m), filename=m[0] + ".zip")
        print(await j("POST", P + "/mods/upload", data=fd))
        await j("POST", P + "/mods/NoBuffHud/toggle")
        await j("POST", P + "/mods/SmarterZombies/source", json={"source": "github.com/undead-lab/smarter-zombies"})
        await j("POST", P + "/preset", json={"stack": [{"id": "z_hard"}, {"id": "s_medium"}]})
        await j("POST", P + "/webmap", json={"enabled": True, "public": True})
        await j("POST", P + "/settings", json={"daylen_dynamic": True, "daylen_ref": 3, "daylen_below": -15, "daylen_above": 20,
                                               "schedule": [{"enabled": True, "days": [1, 2, 3, 4, 5, 6, 7], "time": "05:00", "action": "update_restart", "warn": [15, 5, 1], "message": "Daily restart"}]})
        await j("POST", P + "/server/start")
        for _ in range(40):
            st = await j("GET", P + "/status")
            if st.get("console_connected"):
                break
            await asyncio.sleep(0.5)
        open(os.path.join(DATA, "instances", iid, "userdata", "fake_players"), "w").write("3")
        await j("POST", P + "/command", json={"command": "version"})
        await j("POST", P + "/backups/create")
        await j("POST", "/api/servers", json={"name": "Hardcore Weekend", "clone_from": iid, "port": ov["free_ports"][1]})
        await asyncio.sleep(20)      # let the stats / day-length loop run
        await j("GET", P + "/logcheck?refresh=1")
        await j("POST", P + "/mods/QuickLoot/ack", json={"ok": True})
        return iid


async def shots(iid):
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1360, "height": 860}, device_scale_factor=1)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL)
        await pg.fill("#gatePw", PW); await pg.click("#gateBtn")
        await pg.wait_for_selector("#app:not([hidden])")
        await pg.wait_for_timeout(1500)

        async def shot(name, full=False, clip_sel=None):
            path = f"{OUT}/screenshot-{name}.jpg"
            if clip_sel:
                await pg.locator(clip_sel).screenshot(path=path, type="jpeg", quality=82)
            else:
                await pg.screenshot(path=path, type="jpeg", quality=82, full_page=full)

        async def tab(name):
            await pg.click(f"#tabs button[data-tab={name}]"); await pg.wait_for_timeout(900)
        await tab("mods")
        await pg.click("#mCompat"); await pg.wait_for_timeout(1500)
        await shot("mods")
        await pg.click("#mProblems [data-iss] >> nth=0"); await pg.wait_for_timeout(600)
        await shot("mod-problems", clip_sel="#dlg")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(400)
        await pg.click("#mLog"); await pg.wait_for_timeout(1200)
        await shot("logcheck", clip_sel="#dlg")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(400)
        await pg.fill("#mSearch", "zomb"); await pg.wait_for_timeout(300)
        await pg.fill("#mSearch", ""); await pg.wait_for_timeout(200)
        await pg.click("[data-cfg] >> nth=3"); await pg.wait_for_timeout(700)     # sorted by name: BetterBackpacks, Bigger Hordes, NoBuffHud, ServerTools
        await pg.click("#dlg [data-f] >> nth=0"); await pg.wait_for_timeout(600)
        await shot("mod-config", clip_sel="#dlg")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(500)
        await tab("overview")
        # the sandbox running the fake server has no CPU sensor and the fake process is idle:
        # fill the tiles with typical values of a real server so every tile shows something
        await pg.evaluate("""() => {
          const g = 1024 ** 3;
          S.stats = { ...S.stats, srv_cpu: 23.6, srv_mem: 3.4 * g, cpu_temp: 54, host_cpu: 27.1, host_mem: 6.3 * g, host_mem_total: 15.5 * g,
                      load: [1.42, 1.18, 0.97], disk_used: 73.8 * g, disk_total: 218 * g };
          S.status.meminfo = { fps: "29.84", chunks: "1462", zombies: "38", entities: "117", items: "6" };
          S.status.started_at = Date.now() / 1000 - 3 * 3600 - 1260;
          renderOverview();
        }""")
        await shot("overview")
        await pg.click("[data-q=webmap]"); await pg.wait_for_timeout(900)
        await shot("webmap", clip_sel="#dlg")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(400)
        await tab("automation")
        await pg.locator("#dlPrev").scroll_into_view_if_needed()
        await shot("daylength", clip_sel="#tab-automation .card:has(#dlPrev)")
        await shot("automation", clip_sel="#tab-automation .card >> nth=0")
        await tab("console")
        await shot("console")
        await tab("settings"); await pg.wait_for_timeout(500)
        await shot("settings")
        await pg.click("#btnNew"); await pg.wait_for_timeout(800)
        await pg.select_option("#nClone", iid); await pg.wait_for_timeout(300)
        await shot("duplicate", clip_sel="#dlg")
        await pg.keyboard.press("Escape")
        await pg.click("#btnVersions"); await pg.wait_for_timeout(1200)
        await shot("versions")
        print("page errors:", errs)
        await b.close()


async def main():
    iid = await setup()
    await shots(iid)
asyncio.run(main())
