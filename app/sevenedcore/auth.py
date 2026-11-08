"""Password (scrypt hash, set on first visit or via PANEL_PASSWORD) and long-lived sessions."""
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import os
import secrets

from aiohttp import web

from .util import PANEL_DIR, load_json, now_ts, save_json

PASSWORD_FILE = PANEL_DIR / "password.txt"
SESSIONS_FILE = PANEL_DIR / "sessions.json"
SESSION_TTL = 365 * 24 * 3600
COOKIE = "sevenedcore_session"
SESSIONS = {}
FAILS = {}


def _hash(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def _verify(pw, stored):
    if stored.startswith("scrypt$"):
        _, s, h = stored.split("$")
        return hmac.compare_digest(_hash(pw, base64.b64decode(s)), stored)
    return hmac.compare_digest(pw.encode(), stored.encode())       # legacy plain file


def env_password():
    return os.environ.get("PANEL_PASSWORD", "").strip()


def stored():
    if env_password():
        return env_password()
    if PASSWORD_FILE.exists():
        return PASSWORD_FILE.read_text().strip()
    return None


def set_password(pw):
    PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    PASSWORD_FILE.write_text(_hash(pw) + "\n")
    os.chmod(PASSWORD_FILE, 0o600)


def init():
    SESSIONS.update(load_json(SESSIONS_FILE, {}))
    s = stored()
    if s and not env_password() and not s.startswith("scrypt$"):
        set_password(s)                       # upgrade a plain legacy password to a hash


def save_sessions():
    t = now_ts()
    for k in [k for k, v in SESSIONS.items() if v < t]:
        SESSIONS.pop(k)
    save_json(SESSIONS_FILE, SESSIONS, mode=0o600)


def _cookie(resp, tok):
    resp.set_cookie(COOKIE, tok, max_age=SESSION_TTL, httponly=True, samesite="Strict")


def _new_session(resp):
    tok = secrets.token_urlsafe(32)
    SESSIONS[tok] = now_ts() + SESSION_TTL
    save_sessions()
    _cookie(resp, tok)


def _private(ip):
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False


PUBLIC = ("/api/login", "/api/session", "/api/setup")


@web.middleware
async def middleware(request, handler):
    path = request.path
    if path.startswith("/api/") and request.method != "GET" and request.headers.get("X-Requested-With") != "7edcore":
        raise web.HTTPForbidden(text="CSRF check failed")
    if path.startswith("/api/") and path not in PUBLIC:
        tok = request.cookies.get(COOKIE)
        exp = SESSIONS.get(tok)
        if not exp or exp < now_ts():
            raise web.HTTPUnauthorized(text="Not logged in")
        if exp - now_ts() < SESSION_TTL - 86400:          # sliding expiry, refreshed at most once a day
            SESSIONS[tok] = now_ts() + SESSION_TTL
            save_sessions()
            resp = await handler(request)
            if isinstance(resp, web.StreamResponse) and not resp.prepared:
                _cookie(resp, tok)
            return resp
    return await handler(request)


async def h_session(request):
    tok = request.cookies.get(COOKIE)
    return web.json_response({"ok": bool(SESSIONS.get(tok, 0) > now_ts()), "setup": stored() is None})


async def h_setup(request):
    if stored() is not None:
        raise web.HTTPConflict(text="Password is already set")
    if not _private(request.remote or ""):
        raise web.HTTPForbidden(text="First-time setup is only allowed from your local network")
    pw = str((await request.json()).get("password", ""))
    if len(pw) < 8:
        raise web.HTTPBadRequest(text="Use at least 8 characters")
    set_password(pw)
    resp = web.json_response({"ok": True})
    _new_session(resp)
    return resp


async def h_login(request):
    ip = request.remote or "?"
    f = FAILS.get(ip, [0, 0])
    if f[0] >= 5 and now_ts() - f[1] < 900:
        raise web.HTTPTooManyRequests(text="Too many attempts - try again in 15 minutes")
    s = stored()
    pw = str((await request.json()).get("password", ""))
    if not s or not _verify(pw, s):
        FAILS[ip] = [f[0] + 1 if now_ts() - f[1] < 900 else 1, now_ts()]
        print(f"[7edcore] failed login from {ip}", flush=True)
        await asyncio.sleep(1)
        raise web.HTTPUnauthorized(text="Wrong password")
    FAILS.pop(ip, None)
    resp = web.json_response({"ok": True})
    _new_session(resp)
    return resp


async def h_logout(request):
    SESSIONS.pop(request.cookies.get(COOKIE), None)
    save_sessions()
    resp = web.json_response({"ok": True})
    resp.del_cookie(COOKIE)
    return resp


async def h_password(request):
    if env_password():
        raise web.HTTPConflict(text="The password is set by the PANEL_PASSWORD environment variable")
    d = await request.json()
    if not _verify(str(d.get("current", "")), stored() or ""):
        raise web.HTTPForbidden(text="Current password is wrong")
    new = str(d.get("new", ""))
    if len(new) < 8:
        raise web.HTTPBadRequest(text="Use at least 8 characters")
    set_password(new)
    keep = request.cookies.get(COOKIE)                   # log out every other browser
    for k in [k for k in SESSIONS if k != keep]:
        SESSIONS.pop(k)
    save_sessions()
    return web.json_response({"ok": True})
