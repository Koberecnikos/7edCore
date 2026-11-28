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


def _asset_tag():
    """Changes whenever any static file changes, so browsers never keep an old app.js after an update."""
    import hashlib
    h = hashlib.sha1(__version__.encode())
    for f in sorted(STATIC.iterdir()):
        if f.suffix in (".js", ".css"):
            h.update(f.read_bytes())
    return h.hexdigest()[:10]


INDEX = None


async def h_index(request):
    """The page has <base href> = where the panel lives for this browser: "/" or, behind the Hub portal, "/7d/".
    Every URL in the app is relative to it."""
    global INDEX
    if INDEX is None:
        tag = _asset_tag()
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for name in ("style.css", "i18n.js", "app.js"):
            html = html.replace(f'"static/{name}"', f'"static/{name}?v={tag}"')
        INDEX = html
    return web.Response(text=INDEX.replace("{{base}}", auth.prefix(request) + "/"), content_type="text/html",
                        headers={"Cache-Control": "no-cache, no-store"})


@web.middleware
async def static_cache(request, handler):
    resp = await handler(request)
    if request.path.startswith("/static/"):
        # versioned URLs (?v=) may be cached for a long time, anything else must be revalidated
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable" if request.query.get("v") else "no-cache"
    return resp


def main():
    for d in (PANEL_DIR, INST_ROOT, VERSIONS_DIR, DATA / "home"):
        d.mkdir(parents=True, exist_ok=True)
    auth.init()
    auth.init_local_token()
    hub = Hub()
    hub.load()
    api.HUB = hub
    app = web.Application(middlewares=[static_cache, api.errors, auth.middleware], client_max_size=8 * 1024 ** 3)
    app.router.add_get("/", h_index)
    app.router.add_static("/static/", STATIC)
    app.router.add_get("/api/session", auth.h_session)
    app.router.add_post("/api/setup", auth.h_setup)
    app.router.add_post("/api/login", auth.h_login)
    app.router.add_post("/api/logout", auth.h_logout)
    app.router.add_post("/api/password", auth.h_password)
    app.router.add_get("/api/users", auth.h_users)
    app.router.add_post("/api/users", auth.h_user_create)
    app.router.add_post("/api/users/{name}", auth.h_user_update)
    app.router.add_post("/api/users/{name}/delete", auth.h_user_delete)
    app.router.add_post("/api/local/users", auth.h_local_users)
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
              + (" - open the panel in a browser to create the admin account" if auth.setup_needed() else ""), flush=True)
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
