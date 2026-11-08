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
def L(s): lf.write(time.strftime("%Y-%m-%dT%H:%M:%S") + f" 1.000 INF {s}\n")
L(f"Version: {ver} (b10) Compatibility Version: {ver}, Build: LinuxServer 64 Bit")
world = props.get("GameWorld") or "Navezgane"
world = "Pregen06k01" if world == "RWG" else world
sd = os.path.join(props["UserDataFolder"], "Saves", world, props.get("GameName", "MyGame"))
os.makedirs(sd, exist_ok=True)
open(os.path.join(sd, "main.ttw"), "a").close()
print("fake server stdout hello", flush=True)
stop = None
async def handle(r, w):
    w.write(b"*** Connected with 7DTD server.\r\n"); await w.drain()
    while True:
        line = await r.readline()
        if not line: break
        c = line.decode().strip()
        L(f"Executing command '{c}' by Telnet")
        if c == "version": out = [f"Game version: {ver} Compatibility Version: {ver}"]
        elif c == "lp": out = ["Total of 0 in the game"]
        elif c in ("gt", "gettime"): out = ["Day 3, 14:20"]
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
    L("StartGame done"); L("GameServer.LogOn successful")
    await stop.wait()
    srv.close()
    await asyncio.sleep(0.3)
asyncio.run(main())
