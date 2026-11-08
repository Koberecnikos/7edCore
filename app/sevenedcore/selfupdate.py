"""Panel self-update handshake with the host updater (installed by install.sh).

The panel cannot replace its own container. The host runs `7edcore-update` every few
minutes (systemd timer). Both sides talk through /data/panel/selfupdate.json:
  panel   -> policy (auto | notify | off), request (timestamp of "Update now"), safe (nobody playing)
  updater -> /data/panel/updater.json {"last_run": ts, "image": "...", "result": "..."}
"""
import json
import time

from .util import PANEL_DIR, load_json, save_json

FILE = PANEL_DIR / "selfupdate.json"
UPDATER = PANEL_DIR / "updater.json"
POLICIES = ("auto", "notify", "off")


def _get():
    return {"policy": "auto", "request": 0, "safe": False, "safe_since": 0, **load_json(FILE, {})}


def _put(d):
    # fixed layout so the updater can read it with grep (no jq needed on the host)
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text("{\n" + ",\n".join(f'  "{k}": {json.dumps(v)}' for k, v in d.items()) + "\n}\n")
    tmp.replace(FILE)


def status():
    d, u = _get(), load_json(UPDATER, {})
    return {"policy": d["policy"], "updater": time.time() - float(u.get("last_run") or 0) < 3600,
            "last_run": u.get("last_run"), "result": u.get("result")}


def set_policy(p):
    d = _get()
    d["policy"] = p
    _put(d)


def request():
    d = _get()
    d["request"] = int(time.time())
    _put(d)


def set_safe(safe: bool):
    d = _get()
    if bool(d["safe"]) != safe or not FILE.exists():
        d["safe"] = safe
        d["safe_since"] = int(time.time()) if safe else 0
        _put(d)
