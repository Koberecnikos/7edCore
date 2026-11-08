"""Shared paths, JSON/XML helpers."""
import datetime as dt
import html
import json
import os
import re
import time
import zipfile
from pathlib import Path

from aiohttp import web

DATA = Path(os.environ.get("DATA_DIR", "/data")).resolve()
VERSIONS_DIR = DATA / "versions"          # one game install per Steam branch
INST_ROOT = DATA / "instances"            # one directory per server
PANEL_DIR = DATA / "panel"
TRASH = DATA / "trash"
STEAMCMD = os.environ.get("STEAMCMD", "/opt/steamcmd/steamcmd.sh")
APP_ID = "294420"
SERVER_BIN = os.environ.get("SERVER_BIN", "7DaysToDieServer.x86_64")
PANEL_PORT = int(os.environ.get("PANEL_PORT", "8120"))
MAX_SERVERS = int(os.environ.get("MAX_SERVERS", "4"))
GAME_PORT_BASE = int(os.environ.get("GAME_PORT_BASE", "26900"))   # server k: base + 10*k
WEB_PORT_BASE = int(os.environ.get("WEB_PORT_BASE", "8080"))      # server k: base + k
TELNET_PORT_BASE = 8180                                           # internal only
NCPU = os.cpu_count() or 1
LOGLINE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")
PROP_RE = re.compile(r'<property\s+name="([^"]+)"\s+value="([^"]*)"\s*/>')


def now_ts():
    return time.time()


def stamp():
    return dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data, mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    if mode:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def dir_size(p: Path):
    total = 0
    for root, _dirs, files in os.walk(p):
        for fn in files:
            try:
                total += os.lstat(os.path.join(root, fn)).st_size
            except OSError:
                pass
    return total


def safe_path(rel_: str) -> Path:
    p = (DATA / (rel_ or "").lstrip("/")).resolve()
    if p != DATA and DATA not in p.parents:
        raise web.HTTPForbidden(text="Path outside of the data directory")
    return p


def rel(p: Path) -> str:
    return "/" + str(Path(p).relative_to(DATA)) if Path(p) != DATA else "/"


def cpu_list(spec, default):
    return default if spec in (None, "", "auto") else str(spec)


def parse_hhmm(s):
    h, m = str(s).split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(s)
    return h, m


def slugify(name):
    tr = str.maketrans("áčďéěíňóřšťúůýžäöüß", "acdeeinorstuuyzaous")
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().translate(tr)).strip("-")
    return (s or "server")[:24]


def safe_extract(zpath: Path, dest: Path):
    """Extract a ZIP, refusing entries that would escape dest (zip slip)."""
    dest = Path(dest).resolve()
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            target = (dest / m.filename).resolve()
            if target != dest and dest not in target.parents:
                raise web.HTTPBadRequest(text=f"Unsafe path in ZIP: {m.filename}")
        z.extractall(dest)


# ------------------------------------------------------------------ serverconfig.xml
def read_config_props(cfg: Path):
    """[(name, value, comment)] in file order; commented-out properties are skipped."""
    if not Path(cfg).exists():
        return []
    out, in_comment = [], False
    for line in Path(cfg).read_text(encoding="utf-8", errors="replace").splitlines():
        s = line
        if in_comment:
            if "-->" in s:
                in_comment = False
                s = s.split("-->", 1)[1]
            else:
                continue
        st = s.strip()
        if st.startswith("<!--") and "-->" not in st:
            in_comment = True
            continue
        if st.startswith("<!--"):
            after = st.split("-->", 1)[1]
            if not PROP_RE.search(after):
                continue
            s = after
        m = PROP_RE.search(s)
        if m:
            cm = re.search(r"<!--(.*?)-->", s[m.end():])
            out.append((m.group(1), html.unescape(m.group(2)), cm.group(1).strip() if cm else ""))
    return out


def get_prop(cfg: Path, name, default=""):
    for n, v, _c in read_config_props(cfg):
        if n == name:
            return v
    return default


def write_config_props(cfg: Path, changes: dict):
    """Change values in place, keep formatting and comments; append missing properties."""
    cfg = Path(cfg)
    lines = cfg.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    pending = dict(changes)
    in_comment = False
    for i, line in enumerate(lines):
        st = line.strip()
        if in_comment:
            if "-->" in st:
                in_comment = False
            continue
        if st.startswith("<!--"):
            if "-->" not in st:
                in_comment = True
            continue
        m = PROP_RE.search(line)
        if m and m.group(1) in pending:
            val = html.escape(str(pending.pop(m.group(1))), quote=True)
            lines[i] = line[:m.start(2)] + val + line[m.end(2):]
    text = "".join(lines)
    if pending:
        add = "".join(f'\t<property name="{html.escape(k, quote=True)}" value="{html.escape(str(v), quote=True)}"/>\n'
                      for k, v in pending.items())
        text = text.replace("</ServerSettings>", add + "</ServerSettings>", 1)
    tmp = cfg.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, cfg)
