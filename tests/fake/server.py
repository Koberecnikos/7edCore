#!/usr/bin/env python3
"""Fake 7 Days to Die dedicated server for tests."""
import asyncio, os, re, signal, sys, time
args = sys.argv[1:]
log = args[args.index("-logfile") + 1]
cfg = next(x.split("=", 1)[1] for x in args if x.startswith("-configfile="))
props = dict(re.findall(r'<property\s+name="([^"]+)"\s+value="([^"]*)"', open(cfg).read()))
here = os.path.dirname(os.path.abspath(__file__))
ver = open(os.path.join(here, "fakeversion.txt")).read().strip()
lf = open(log, "a", buffering=1)
def L(s): lf.write(time.strftime("%Y-%m-%dT%H:%M:%S") + f" 1.000 {s if s[:4] in ('ERR ', 'WRN ', 'EXC ') else 'INF ' + s}\n")
L(f"Version: {ver} (b10) Compatibility Version: {ver}, Build: LinuxServer 64 Bit")
mods_dir = os.path.join(props["UserDataFolder"], "Mods")
for m in sorted(os.listdir(mods_dir)) if os.path.isdir(mods_dir) else []:
    if m.startswith("Broken") or os.path.exists(os.path.join(mods_dir, m, "FAKE_BROKEN")):          # what the real game prints for a mod built for another version
        L(f"ERR [MODS]     Failed initializing ModAPI instance on mod '{m}' in assembly {m}.Boot (in {mods_dir}/{m}/{m}.dll)")
        L("EXC This update supports native 7D2D 3.1, 3.2 and 3.3.")
        L(f'WRN XML patch for "items.xml" from mod "{m}" did not apply: <remove xpath="/items/item[@name=\'gone\']"  (line 2 at pos 3)')
        L("ERR XML loader: Loading and parsing 'items.xml' failed")
        L(f"EXC No item class '{m}.ItemClassThing, {m} found!")
        lf.write("ERROR: Shader Standard shader is not supported on this GPU (none of subshaders/fallbacks are suitable)\n")
world = props.get("GameWorld") or "Navezgane"
world = "Pregen06k01" if world == "RWG" else world
sd = os.path.join(props["UserDataFolder"], "Saves", world, props.get("GameName", "MyGame"))
os.makedirs(sd, exist_ok=True)
open(os.path.join(sd, "main.ttw"), "a").close()
adm = os.path.join(props["UserDataFolder"], "Saves", props.get("AdminFileName") or "serveradmin.xml")
if not os.path.exists(adm):
    open(adm, "w").write("""<?xml version="1.0" encoding="UTF-8"?>
<!-- example: <webmodules /> <module name="web.map" permission_level="0" /> -->
<adminTools>
  <users>
  </users>
  <apitokens>
    <!-- <token name="adminuser1" secret="supersecrettoken" permission_level="0" /> -->
  </apitokens>
  <webmodules />
  <webusers />
</adminTools>
""")
daylen = int(props.get("DayNightLength") or 60)
gm0, t0 = 2 * 1440 + 14 * 60 + 20, time.time()          # Day 3, 14:20
def game_minutes(): return gm0 + (time.time() - t0) / 60 * 1440 / daylen * float(os.environ.get("FAKE_TIMESCALE", "1"))
def nplayers():
    try: return int(open(os.path.join(props["UserDataFolder"], "fake_players")).read())
    except (OSError, ValueError): return 0
print("[Steamworks.NET] SteamAPI initialized, GameServer started", flush=True)
stop = None
async def handle(r, w):
    global daylen, gm0, t0
    w.write(b"*** Connected with 7DTD server.\r\n"); await w.drain()
    while True:
        line = await r.readline()
        if not line: break
        c = line.decode().strip()
        L(f"Executing command '{c}' by Telnet")
        if c == "version": out = [f"Game version: {ver} Compatibility Version: {ver}"]
        elif c == "lp":
            n = nplayers()
            out = [f"{k + 1}. id={171 + k}, Player{k + 1}, pos=(1.0, 2.0, 3.0), rot=(0.0, 0.0, 0.0), remote=True, health=100, deaths=0, zombies={k}, players=0, score=0, level=5, pltfmid=Steam_7656119800000000{k}, crossid=EOS_000{k}, ip=10.0.0.{k + 2}, ping=20" for k in range(n)] + [f"Total of {n} in the game"]
        elif c in ("gt", "gettime"):
            g = int(game_minutes())
            out = [f"Day {g // 1440 + 1}, {g % 1440 // 60:02d}:{g % 60:02d}"]
        elif c.startswith("setgamepref DayNightLength "):
            g = game_minutes(); daylen = int(c.split()[-1]); gm0, t0 = g, time.time()
            out = [f"DayNightLength set to {daylen}"]
        elif c.startswith("settime "):
            d, h, m = (int(x) for x in c.split()[1:4]); gm0, t0 = (d - 1) * 1440 + h * 60 + m, time.time()
            out = ["Set time"]
        elif c == "mem": out = ["Time: 1.00m FPS: 30.00 Heap: 512.0MB Max: 600.0MB Chunks: 100 CGO: 10 Ply: 0 Zom: 0 Ent: 1 (2) Items: 0 CO: 0 RSS: 900.0MB"]
        elif c == "saveworld": out = ["World saved"]
        elif c == "shutdown": out = ["Shutting server down..."]
        else: out = [f"OK {c}"]
        for o in out: w.write((o + "\r\n").encode())
        await w.drain()
        if c == "shutdown":
            L("Shutdown game"); stop.set()
async def main():
    global stop
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    await asyncio.sleep(float(os.environ.get("FAKE_BOOT", "1")))
    srv = await asyncio.start_server(handle, "127.0.0.1", int(props.get("TelnetPort", 8081)))
    if props.get("WebDashboardEnabled") == "true":
        async def webh(r, w):
            await r.readline()
            w.write(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n<html>dashboard</html>"); await w.drain(); w.close()
        await asyncio.start_server(webh, "127.0.0.1", int(props.get("WebDashboardPort", 8080)))
        L(f"Started Webserver on port {props.get('WebDashboardPort')}")
    L("StartGame done"); L("GameServer.LogOn successful")
    await stop.wait()
    srv.close()
    await asyncio.sleep(0.3)
asyncio.run(main())
