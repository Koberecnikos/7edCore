#!/usr/bin/env python3
"""Save the world of every running 7edCore server (telnet "saveworld") without stopping it.
Meant for UPS / power-loss hooks:  docker exec 7edcore python3 /app/save.py"""
import glob
import os
import re
import socket
import time

DATA = os.environ.get("DATA_DIR", "/data")


def save(cfg_path):
    try:
        text = open(cfg_path, errors="replace").read()
    except OSError:
        return None
    m = re.search(r'name="TelnetPort"\s+value="(\d+)"', text)
    port = int(m.group(1)) if m else 8081
    m = re.search(r'name="TelnetPassword"\s+value="([^"]*)"', text)
    pw = m.group(1) if m else ""
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
    except OSError:
        return None                       # this server is not running
    s.settimeout(1)
    if pw:
        time.sleep(0.5)
        s.sendall((pw + "\r\n").encode())
    s.sendall(b"saveworld\r\n")
    end = time.time() + 15
    while time.time() < end:
        try:
            if not s.recv(4096):
                break
        except socket.timeout:
            pass
    s.close()
    return port


done = [p for p in (save(c) for c in sorted(glob.glob(f"{DATA}/instances/*/config/serverconfig.xml"))) if p]
print(f"saveworld sent to telnet ports: {done}" if done else "no server is running - nothing to save")
