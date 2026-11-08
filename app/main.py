#!/usr/bin/env python3
"""7edCore - web panel for 7 Days to Die dedicated servers."""
import asyncio
import signal
from pathlib import Path

from aiohttp import web

from sevenedcore import __version__, api, auth
from sevenedcore.hub import Hub
from sevenedcore.util import DATA, INST_ROOT, PANEL_DIR, PANEL_PORT, VERSIONS_DIR

STATIC = Path(__file__).resolve().parent / "static"


async def h_index(request):
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


def main():
    for d in (PANEL_DIR, INST_ROOT, VERSIONS_DIR, DATA / "home"):
        d.mkdir(parents=True, exist_ok=True)
    auth.init()
    hub = Hub()
    hub.load()
    api.HUB = hub
    app = web.Application(middlewares=[api.errors, auth.middleware], client_max_size=8 * 1024 ** 3)
    app.router.add_get("/", h_index)
    app.router.add_static("/static/", STATIC)
    app.router.add_get("/api/session", auth.h_session)
    app.router.add_post("/api/setup", auth.h_setup)
    app.router.add_post("/api/login", auth.h_login)
    app.router.add_post("/api/logout", auth.h_logout)
    app.router.add_post("/api/password", auth.h_password)
    api.routes(app)

    async def on_startup(_app):
        asyncio.create_task(hub.stats_loop())
        asyncio.create_task(hub.scheduler_loop())
        asyncio.create_task(hub.updates_loop())
        for inst in hub.instances.values():
            a = inst.settings.get("autostart")
            if hub.steam.installed(inst.branch) and (a == "always" or (a == "last" and inst.pstate.get("was_running"))):
                inst.note(f"Autostart ({a})")
                api.bg(inst.start(reason="autostart"), "Autostart", inst)

    app.on_startup.append(on_startup)

    async def run():
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PANEL_PORT).start()
        print(f"[7edcore] v{__version__} on :{PANEL_PORT}, data {DATA}, servers: {', '.join(hub.order)}"
              + ("" if auth.stored() else " - open the panel in a browser to set the admin password"), flush=True)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        print("[7edcore] shutting down - saving and stopping all servers", flush=True)
        await asyncio.gather(*(i.stop(user=False, reason="panel shutdown") for i in hub.instances.values()),
                             return_exceptions=True)
        await runner.cleanup()

    asyncio.run(run())


if __name__ == "__main__":
    main()
