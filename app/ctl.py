#!/usr/bin/env python3
"""7edcore - command line for scripts, UPS and power hooks.

On the host:          7edcore <command>          (wrapper installed by install.sh)
Inside the container: docker exec 7edcore 7edcore <command>

Commands:
  status                  servers, state, players (add --json for machine output)
  save                    save the world of every running server (no restart)
  stop-all [reason]       save and stop every running server, remember which ones
  resume                  start the servers that stop-all stopped
  start|stop|restart ID   one server (ID as shown by status)
  request-update          ask the host updater to update 7edCore now
Exit code 0 = OK, 1 = error, 2 = panel not reachable.
"""
import json
import os
import sys
import urllib.error
import urllib.request

DATA = os.environ.get("DATA_DIR", "/data")
PORT = os.environ.get("PANEL_PORT", "8120")


def call(method, path, body=None, timeout=900):
    try:
        token = open(f"{DATA}/panel/local.token").read().strip()
    except OSError:
        raise ConnectionError("panel token not found - is the panel running?")
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/local/{path}", method=method,
                                 data=json.dumps(body or {}).encode() if method == "POST" else None,
                                 headers={"X-7edCore-Local": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except Exception:
            msg = e.reason
        raise RuntimeError(msg)
    except (urllib.error.URLError, OSError) as e:
        raise ConnectionError(f"panel not reachable: {e}")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "status":
            d = call("GET", "status")
            if "--json" in args:
                print(json.dumps(d, indent=2))
            else:
                print(f"7edCore {d['version']}")
                for s in d["servers"]:
                    extra = f"  pending: {s['pending']}" if s["pending"] else ""
                    print(f"  {s['id']:<20} {s['state']:<9} players {s['players']:<3} {s['game'] or s['branch']:<12} port {s['port']}{extra}")
                if d["power_stopped"]:
                    print("  stopped by stop-all: " + ", ".join(d["power_stopped"]))
        elif cmd == "save":
            try:
                d = call("POST", "save", timeout=120)
                print("saved: " + (", ".join(d["saved"]) or "nothing is running"))
            except ConnectionError:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from save import save_all
                ports = save_all()
                print(f"panel not reachable - saveworld sent directly to telnet ports {ports}")
        elif cmd == "stop-all":
            d = call("POST", "stop-all", {"reason": " ".join(args) or "7edcore stop-all"})
            print("stopped: " + (", ".join(d["stopped"]) or "nothing was running"))
        elif cmd == "resume":
            d = call("POST", "resume")
            print("started: " + (", ".join(d["started"]) or "nothing to resume"))
            for k, v in d["failed"].items():
                print(f"  {k}: {v}", file=sys.stderr)
            return 1 if d["failed"] else 0
        elif cmd in ("start", "stop", "restart"):
            if len(args) != 1:
                print(f"usage: 7edcore {cmd} SERVER_ID", file=sys.stderr)
                return 1
            d = call("POST", f"s/{args[0]}/{cmd}")
            print(f"{args[0]}: {d['state']}")
        elif cmd == "request-update":
            call("POST", "request-update")
            print("update requested")
        else:
            print(f"unknown command: {cmd} (see 7edcore help)", file=sys.stderr)
            return 1
    except ConnectionError as e:
        print(str(e), file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
