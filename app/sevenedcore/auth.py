"""User accounts, roles and long-lived sessions.

Roles:
  admin     everything (servers, game versions, files, users, panel settings)
  operator  run servers they have access to: start/stop/restart, console, players, quick actions,
            create/restore backups. No settings, mods, files or deletes.
  viewer    read-only access to the servers they have access to
Each non-admin account lists the servers it may see ("*" = all).
First visit from the local network creates the first admin. PANEL_PASSWORD (env) keeps an
"admin" account with that password. Lost password: `7edcore user reset NAME` on the host."""
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import os
import re
import secrets

from aiohttp import web

from .util import PANEL_DIR, load_json, now_ts, save_json

USERS_FILE = PANEL_DIR / "users.json"
LEGACY_PASSWORD_FILE = PANEL_DIR / "password.txt"
SESSIONS_FILE = PANEL_DIR / "sessions.json"
SESSION_TTL = 365 * 24 * 3600
COOKIE = "sevenedcore_session"
ROLES = ("admin", "operator", "viewer")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,32}$")
USERS = {}          # name -> {"hash", "role", "servers": "*" | [ids], "created"}
SESSIONS = {}       # token -> {"exp", "user"}
FAILS = {}


def _hash(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def _verify(pw, stored):
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, s, _h = stored.split("$")
    return hmac.compare_digest(_hash(pw, base64.b64decode(s)), stored)


def env_password():
    return os.environ.get("PANEL_PASSWORD", "").strip()


def save_users():
    save_json(USERS_FILE, USERS, mode=0o600)


def check_password_rules(pw):
    if len(pw) < 8:
        raise web.HTTPBadRequest(text="Use at least 8 characters")


def add_user(name, pw, role="viewer", servers="*"):
    if not NAME_RE.match(name or ""):
        raise web.HTTPBadRequest(text="User name: 2-32 letters, numbers, . _ -")
    if name in USERS:
        raise web.HTTPConflict(text="That user already exists")
    if role not in ROLES:
        raise web.HTTPBadRequest(text="Role: admin, operator or viewer")
    check_password_rules(pw)
    USERS[name] = {"hash": _hash(pw), "role": role, "servers": servers, "created": now_ts()}
    save_users()


def admins():
    return [n for n, u in USERS.items() if u["role"] == "admin"]


def init():
    USERS.update(load_json(USERS_FILE, {}))
    if not USERS and LEGACY_PASSWORD_FILE.exists():           # single-password panels -> account "admin"
        old = LEGACY_PASSWORD_FILE.read_text().strip()
        USERS["admin"] = {"hash": old if old.startswith("scrypt$") else _hash(old), "role": "admin",
                          "servers": "*", "created": now_ts()}
        save_users()
        LEGACY_PASSWORD_FILE.rename(LEGACY_PASSWORD_FILE.with_suffix(".txt.migrated"))
        print("[7edcore] password migrated to the user account 'admin'", flush=True)
    pw = env_password()
    if pw:
        u = USERS.get("admin")
        if not u or not _verify(pw, u["hash"]) or u["role"] != "admin":
            USERS["admin"] = {"hash": _hash(pw), "role": "admin", "servers": "*", "created": now_ts()}
            save_users()
    for tok, s in load_json(SESSIONS_FILE, {}).items():
        if isinstance(s, dict) and s.get("user") in USERS:     # old single-password sessions are dropped
            SESSIONS[tok] = s


def setup_needed():
    return not USERS


def save_sessions():
    t = now_ts()
    for k in [k for k, v in SESSIONS.items() if v["exp"] < t or v["user"] not in USERS]:
        SESSIONS.pop(k)
    save_json(SESSIONS_FILE, SESSIONS, mode=0o600)


def drop_sessions(user, keep=None):
    for k in [k for k, v in SESSIONS.items() if v["user"] == user and k != keep]:
        SESSIONS.pop(k)
    save_sessions()


def _cookie(resp, tok):
    resp.set_cookie(COOKIE, tok, max_age=SESSION_TTL, httponly=True, samesite="Strict")


def _new_session(resp, user):
    tok = secrets.token_urlsafe(32)
    SESSIONS[tok] = {"exp": now_ts() + SESSION_TTL, "user": user}
    save_sessions()
    _cookie(resp, tok)


def _private(ip):
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False


def public_user(name):
    u = USERS[name]
    return {"name": name, "role": u["role"], "servers": u["servers"]}


# ------------------------------------------------------------------ permissions
ADMIN_ONLY = re.compile(r"^/api/(global|selfupdate|users|files|exports|updates/check|servers$)")
SERVER_PATH = re.compile(r"^/api/s/([^/]+)(/.*)?$")
VIEWER_DENY_GET = re.compile(r"^/(config|export)$")
OPERATOR_POST = re.compile(r"^/(server/\w+|command|quick/\w+|backups/(create|restore))$")


def can_see(user, iid):
    s = USERS[user]["servers"]
    return USERS[user]["role"] == "admin" or s == "*" or iid in s


def allowed(user, method, path):
    u = USERS.get(user)
    if not u:
        return False
    if u["role"] == "admin" or path in ("/api/password", "/api/logout", "/api/me"):
        return True
    if ADMIN_ONLY.match(path):
        return False
    m = SERVER_PATH.match(path)
    if m:
        if not can_see(user, m.group(1)):
            return False
        sub = m.group(2) or ""
        if method == "GET":
            return not VIEWER_DENY_GET.match(sub)
        return u["role"] == "operator" and bool(OPERATOR_POST.match(sub))
    if path.startswith("/api/versions"):
        return method == "GET"
    return method == "GET"                        # overview, presets, configmeta ...


# ------------------------------------------------------------------ middleware + handlers
LOCAL_TOKEN_FILE = PANEL_DIR / "local.token"
LOCAL_TOKEN = None
PUBLIC = ("/api/login", "/api/session", "/api/setup")


def init_local_token():
    """Token for the `7edcore` command line tool inside the container (docker exec)."""
    global LOCAL_TOKEN
    LOCAL_TOKEN = secrets.token_urlsafe(32)
    LOCAL_TOKEN_FILE.write_text(LOCAL_TOKEN)
    os.chmod(LOCAL_TOKEN_FILE, 0o600)


@web.middleware
async def middleware(request, handler):
    path = request.path
    if path.startswith("/api/local/"):
        tok = request.headers.get("X-7edCore-Local", "")
        if not LOCAL_TOKEN or request.remote not in ("127.0.0.1", "::1") or not secrets.compare_digest(tok, LOCAL_TOKEN):
            raise web.HTTPForbidden(text="Local API: use the 7edcore command inside the container")
        return await handler(request)
    if path.startswith("/api/") and request.method != "GET" and request.headers.get("X-Requested-With") != "7edcore":
        raise web.HTTPForbidden(text="CSRF check failed")
    if path.startswith("/api/") and path not in PUBLIC:
        tok = request.cookies.get(COOKIE)
        s = SESSIONS.get(tok)
        if not s or s["exp"] < now_ts() or s["user"] not in USERS:
            raise web.HTTPUnauthorized(text="Not logged in")
        request["user"] = s["user"]
        if not allowed(s["user"], request.method, path):
            raise web.HTTPForbidden(text=f"Your role ({USERS[s['user']]['role']}) cannot do this")
        if s["exp"] - now_ts() < SESSION_TTL - 86400:          # sliding expiry, refreshed at most once a day
            s["exp"] = now_ts() + SESSION_TTL
            save_sessions()
            resp = await handler(request)
            if isinstance(resp, web.StreamResponse) and not resp.prepared:
                _cookie(resp, tok)
            return resp
    return await handler(request)


async def h_session(request):
    s = SESSIONS.get(request.cookies.get(COOKIE))
    ok = bool(s and s["exp"] > now_ts() and s["user"] in USERS)
    return web.json_response({"ok": ok, "setup": setup_needed(), "user": public_user(s["user"]) if ok else None})


async def h_setup(request):
    if not setup_needed():
        raise web.HTTPConflict(text="The panel is already set up")
    if not _private(request.remote or ""):
        raise web.HTTPForbidden(text="First-time setup is only allowed from your local network")
    d = await request.json()
    name = str(d.get("username", "")).strip() or "admin"
    add_user(name, str(d.get("password", "")), "admin", "*")
    resp = web.json_response({"ok": True})
    _new_session(resp, name)
    return resp


async def h_login(request):
    ip = request.remote or "?"
    f = FAILS.get(ip, [0, 0])
    if f[0] >= 5 and now_ts() - f[1] < 900:
        raise web.HTTPTooManyRequests(text="Too many attempts - try again in 15 minutes")
    d = await request.json()
    name = str(d.get("username", "")).strip() or "admin"
    u = USERS.get(name)
    if not u or not _verify(str(d.get("password", "")), u["hash"]):
        FAILS[ip] = [f[0] + 1 if now_ts() - f[1] < 900 else 1, now_ts()]
        print(f"[7edcore] failed login for '{name[:32]}' from {ip}", flush=True)
        await asyncio.sleep(1)
        raise web.HTTPUnauthorized(text="Wrong user name or password")
    FAILS.pop(ip, None)
    resp = web.json_response({"ok": True})
    _new_session(resp, name)
    return resp


async def h_logout(request):
    SESSIONS.pop(request.cookies.get(COOKIE), None)
    save_sessions()
    resp = web.json_response({"ok": True})
    resp.del_cookie(COOKIE)
    return resp


async def h_password(request):
    """Change your own password; other browsers of this user are signed out."""
    name = request["user"]
    if name == "admin" and env_password():
        raise web.HTTPConflict(text="The admin password is set by the PANEL_PASSWORD environment variable")
    d = await request.json()
    if not _verify(str(d.get("current", "")), USERS[name]["hash"]):
        raise web.HTTPForbidden(text="Current password is wrong")
    new = str(d.get("new", ""))
    check_password_rules(new)
    USERS[name]["hash"] = _hash(new)
    save_users()
    drop_sessions(name, keep=request.cookies.get(COOKIE))
    return web.json_response({"ok": True})


# ------------------------------------------------------------------ user management (admin)
def _servers_value(v):
    if v in ("*", None, ""):
        return "*"
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return v
    raise web.HTTPBadRequest(text='servers: "*" or a list of server ids')


async def h_users(request):
    return web.json_response({"users": [public_user(n) | {"created": USERS[n].get("created")} for n in sorted(USERS)],
                              "roles": ROLES})


async def h_user_create(request):
    d = await request.json()
    add_user(str(d.get("username", "")).strip(), str(d.get("password", "")), str(d.get("role", "viewer")),
             _servers_value(d.get("servers", "*")))
    return web.json_response({"ok": True})


async def h_user_update(request):
    name = request.match_info["name"]
    if name not in USERS:
        raise web.HTTPNotFound(text="No such user")
    d = await request.json()
    u = USERS[name]
    if "role" in d:
        if d["role"] not in ROLES:
            raise web.HTTPBadRequest(text="Role: admin, operator or viewer")
        if u["role"] == "admin" and d["role"] != "admin" and admins() == [name]:
            raise web.HTTPConflict(text="The last admin cannot be demoted")
        u["role"] = d["role"]
    if "servers" in d:
        u["servers"] = _servers_value(d["servers"])
    if d.get("password"):
        check_password_rules(str(d["password"]))
        u["hash"] = _hash(str(d["password"]))
        drop_sessions(name, keep=request.cookies.get(COOKIE) if name == request["user"] else None)
    save_users()
    return web.json_response({"ok": True})


async def h_user_delete(request):
    name = request.match_info["name"]
    if name not in USERS:
        raise web.HTTPNotFound(text="No such user")
    if USERS[name]["role"] == "admin" and admins() == [name]:
        raise web.HTTPConflict(text="The last admin cannot be deleted")
    USERS.pop(name)
    save_users()
    drop_sessions(name)
    return web.json_response({"ok": True})


# ------------------------------------------------------------------ local (7edcore user ...)
async def h_local_users(request):
    d = await request.json() if request.can_read_body else {}
    op, name = d.get("op", "list"), str(d.get("name", "")).strip()
    if op == "list":
        return web.json_response({"users": [public_user(n) for n in sorted(USERS)]})
    if op in ("add", "reset"):
        pw = secrets.token_urlsafe(9)
        if op == "add":
            add_user(name, pw, d.get("role") or "admin", "*")
        else:
            if name not in USERS:
                raise web.HTTPNotFound(text=f"No such user: {name} (existing: {', '.join(sorted(USERS)) or 'none'})")
            USERS[name]["hash"] = _hash(pw)
            save_users()
            drop_sessions(name)
        return web.json_response({"ok": True, "name": name, "password": pw})
    if op == "role":
        if name not in USERS or d.get("role") not in ROLES:
            raise web.HTTPBadRequest(text="usage: 7edcore user role NAME admin|operator|viewer")
        if USERS[name]["role"] == "admin" and d["role"] != "admin" and admins() == [name]:
            raise web.HTTPConflict(text="The last admin cannot be demoted")
        USERS[name]["role"] = d["role"]
        save_users()
        return web.json_response({"ok": True})
    if op == "delete":
        if name not in USERS:
            raise web.HTTPNotFound(text="No such user")
        if USERS[name]["role"] == "admin" and admins() == [name]:
            raise web.HTTPConflict(text="The last admin cannot be deleted")
        USERS.pop(name)
        save_users()
        drop_sessions(name)
        return web.json_response({"ok": True})
    raise web.HTTPBadRequest(text="op: list, add, reset, role, delete")
