"""Read a 7 Days to Die server log and explain what went wrong: which mod failed and why,
which XML files did not load, and which messages are normal noise on a dedicated server."""
import re
from pathlib import Path

LOGPFX = re.compile(r"^(?:\d\d:\d\d:\d\d)?(?:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d \d+\.\d+ )?")
MODPATH = re.compile(r"/Mods/([^/]+)/")

# messages that look scary but are normal for a headless dedicated server
HARMLESS = [
    (re.compile(r"shader is not supported on this GPU|^WARNING: Shader|All subshaders removed|Did you use #pragma only_renderers|"
                r"If subshaders removal was intentional"), "Shaders: the server runs without graphics"),
    (re.compile(r"was too large for graphics device maximum supported texture size"), "Textures: the server runs without graphics"),
    (re.compile(r"DeviceId access credentials already exist"), "EOS login note (always printed)"),
    (re.compile(r"S_API FAIL\] Tried to access Steam interface"), "Steam API note (always printed)"),
    (re.compile(r"HighwayPlanner|SpawnMarkerPartsAndPrefabs|Tile starting with rwg_tile|TownPlanner"), "World generator notes (RWG)"),
    (re.compile(r"WRN save folder does not exist"), "New world - nothing saved yet"),
    (re.compile(r"WRN Next Airdrop"), "Airdrop timer"),
    (re.compile(r"The referenced script on this Behaviour .* is missing"), "Unity: client-only component on the server"),
    (re.compile(r"is missing the UnityEngine.Scripting.Preserve attribute"), "Console-platform note"),
    (re.compile(r"TypeRef ResolutionScope not yet handled"), "Mono runtime note"),
    (re.compile(r"already registered from ConsoleCmd"), "Two mods/commands want the same console alias - the first one wins"),
]
NOISE = re.compile(r"^\s+at |^(UnityEngine\.|Log:|Mod:InitModCode|ModManager:|GameManager:|ReflectionHelpers:|System\.Object:|"
                   r"<\w|<>c__|\d+\. |Successfully loaded Types:|Exceptions:|Rethrow as|Parameter name:|###|EXC |"
                   r"System\.TypeLoadException|ReflectionTypeLoadException|Could not load type of field)")
ASM_IN = re.compile(r"assembly ([\w.-]+)")


def _norm(line):
    return LOGPFX.sub("", line.rstrip("\r\n"))


class ModMap:
    """Resolve mod names / assembly names / folders seen in the log to mod folders."""

    def __init__(self, mods):                     # mods: [{"folder", "name", "path"(Path), "id"}]
        self.mods = {m["folder"]: m for m in mods}
        self.by = {}
        for m in mods:
            for k in (m["folder"], m.get("name"), m.get("id")):
                if k:
                    self.by[k.lower()] = m["folder"]
            for dll in Path(m["path"]).rglob("*.dll"):
                self.by.setdefault(dll.stem.lower(), m["folder"])
        self._texts = None

    def find(self, key):
        if not key:
            return None
        k = key.strip().strip("'\"").lower()
        if k in self.by:
            return self.by[k]
        k2 = k.split(".")[0]
        return self.by.get(k2)

    def texts(self):
        if self._texts is None:
            self._texts = {}
            for f, m in self.mods.items():
                parts = []
                for x in Path(m["path"]).rglob("*.xml"):
                    try:
                        parts.append(x.read_text(encoding="utf-8", errors="replace"))
                    except OSError:
                        pass
                self._texts[f] = "\n".join(parts)
        return self._texts

    def defining(self, name):
        """Mods whose XML defines something called `name`."""
        rx = re.compile(r'name\s*=\s*["\']' + re.escape(name) + r'["\']')
        return sorted(f for f, t in self.texts().items() if rx.search(t))

    def mentioning(self, token):
        return sorted(f for f, t in self.texts().items() if token in t)


def analyze(lines, mods):
    mm = ModMap(mods)
    per_mod, general, harmless = {}, {}, {}
    xml_failed = []

    def add(folder, sev, kind, text, detail=""):
        lst = per_mod.setdefault(folder, [])
        for it in lst:
            if it["kind"] == kind and it["text"] == text:
                it["count"] += 1
                return
        lst.append({"severity": sev, "kind": kind, "text": text, "detail": detail, "count": 1})

    def gen(sev, text, detail=""):
        g = general.setdefault(text, {"severity": sev, "text": text, "detail": detail, "count": 0})
        g["count"] += 1

    L = [_norm(x) for x in lines]
    n = len(L)

    def next_exc(i, look=6):
        for j in range(i + 1, min(n, i + 1 + look)):
            if L[j].startswith("EXC "):
                return L[j][4:].strip()
        return ""

    harmony_user = None
    for i, s in enumerate(L):
        if not s:
            continue
        m = re.search(r"Failed initializing ModAPI instance on mod '([^']+)'", s)
        if m:
            f = mm.find(m.group(1)) or m.group(1)
            add(f, "error", "code_failed", "The mod's code did not start", next_exc(i))
            continue
        m = re.search(r"Failed creating ModAPI instance from assembly (\S+)", s)
        if m:
            pm = MODPATH.search(s)
            f = (pm and pm.group(1)) or mm.find(m.group(1)) or m.group(1)
            add(f, "error", "code_failed", "The mod's code did not start", next_exc(i))
            continue
        m = re.search(r"Error loading types from assembly (\S+)", s)
        if m:
            pm = MODPATH.search(s)
            f = (pm and pm.group(1)) or mm.find(m.group(1)) or m.group(1)
            why = ""
            for j in range(i + 1, min(n, i + 8)):
                t = re.search(r"expected class '([^']+)'", L[j])
                if t:
                    why = f"uses game type {t.group(1)}, which does not exist in this game version"
                    break
            add(f, "error", "types_failed", "Built for another game version - " + (why or "its classes could not be loaded"))
            continue
        m = re.search(r'### Exception from user "([^"]+)"', s)
        if m:
            harmony_user = m.group(1)
            continue
        m = re.search(r"AccessTools\.DeclaredMethod: Could not find method for type (\S+) and name (\S+)", s)
        if m:
            f = mm.find(harmony_user) if harmony_user else None
            for j in range(i + 1, min(n, i + 6)):
                u = re.search(r'### Exception from user "([^"]+)"', L[j])
                if u:
                    f = f or mm.find(u.group(1))
            add(f or "?", "error", "harmony_target",
                f"Patches {m.group(1)}.{m.group(2)}, which does not exist in this game version")
            continue
        m = re.search(r'XML patch for "([^"]+)" from mod "([^"]+)" did not apply: (.*)', s)
        if m:
            f = mm.find(m.group(2)) or m.group(2)
            add(f, "warning", "patch_not_applied", f"A change to {m.group(1)} did not apply (that part of the mod has no effect)",
                m.group(3)[:300])
            continue
        m = re.search(r"XML loader: Loading and parsing '([^']+)' failed", s)
        if m:
            file, why = m.group(1), next_exc(i)
            culprit = None
            c = re.search(r"class '[\w.]+, ([\w.-]+)'? found|class '([\w.]+), ([\w.-]+)", why)
            if c:
                culprit = mm.find(c.group(1) or c.group(3))
            nm = re.search(r"name '([^']+)'", why)
            defined_by = mm.defining(nm.group(1)) if nm else []
            xml_failed.append({"file": file, "why": why, "culprit": culprit, "missing": nm.group(1) if nm else None,
                               "defined_by": defined_by})
            if culprit:
                add(culprit, "error", "xml_failed", f"Breaks loading of {file}", why)
            continue
        m = re.search(r"Could not instantiate class\s*([\w.]+), ([\w.-]+)' for (\w+) '([^']+)'", s)
        if m:
            f = mm.find(m.group(2)) or m.group(2)
            add(f, "error", "missing_class", f"{m.group(3)} '{m.group(4)}' needs code ({m.group(1)}) that did not load")
            continue
        m = re.search(r"Mod reference for a mod that is not loaded: '([^']+)'", s)
        if m:
            dep = m.group(1)
            users = mm.mentioning(f"@modfolder({dep})") or ["?"]
            for f in users:
                add(f, "error", "missing_dependency", f"Needs the mod {dep}, which is not installed")
            continue
        if re.search(r"Loading AssetBundle .*@modfolder\(([^)]+)\).* failed: Parent folder not found", s):
            continue                                   # counted by the dependency message above
        m = re.search(r"Type:([\w.]+), ([\w.-]+) was missing when we looked it up", s)
        if m:
            f = mm.find(m.group(2))
            if f:
                add(f, "error", "missing_class", f"Its code class {m.group(1)} is missing (the DLL did not load)")
                continue
        if not re.match(r"(ERR|EXC|WRN) |ERROR:|WARNING:|\[S_API FAIL\]", s) and "Exception" not in s[:60]:
            continue
        hm = next((label for rx, label in HARMLESS if rx.search(s)), None)
        if hm:
            harmless[hm] = harmless.get(hm, 0) + 1
            continue
        if NOISE.match(s):
            continue
        pm = MODPATH.search(s)
        f = pm.group(1) if pm and pm.group(1) in mm.mods else None
        if not f:
            am = ASM_IN.search(s)
            f = mm.find(am.group(1)) if am else None
        sev = "warning" if s.startswith(("WRN", "WARNING")) else "error"
        text = re.sub(r"\d+(\.\d+)?", "#", s[:240]) if sev == "warning" else s[:240]
        if f:
            add(f, sev, "log", re.sub(r"^(ERR|WRN) ", "", text))
        else:
            gen(sev, text, next_exc(i) if sev == "error" else "")
    # consequences of a failed XML file: everything defined later is missing
    for x in xml_failed:
        if x["culprit"]:
            continue                                   # already listed under that mod
        msg = f"{x['file']} failed to load"
        if x["culprit"]:
            msg += f" because of {x['culprit']}"
        if x["missing"]:
            msg += f" - '{x['missing']}' is missing" + (f" (defined by {', '.join(x['defined_by'])}, probably not loaded because an earlier file failed)" if x["defined_by"] else "")
        gen("error", msg, x["why"])
    for f, lst in per_mod.items():
        lst.sort(key=lambda it: {"error": 0, "warning": 1}.get(it["severity"], 2))
    summary = {"mods_error": sorted(f for f, l in per_mod.items() if any(i["severity"] == "error" for i in l)),
               "mods_warning": sorted(f for f, l in per_mod.items() if l and not any(i["severity"] == "error" for i in l)),
               "xml_failed": [x["file"] for x in xml_failed],
               "errors": sum(1 for g in general.values() if g["severity"] == "error"),
               "harmless": sum(harmless.values())}
    return {"mods": per_mod, "general": sorted(general.values(), key=lambda g: (g["severity"] != "error", -g["count"])),
            "harmless": [{"text": k, "count": v} for k, v in sorted(harmless.items(), key=lambda kv: -kv[1])],
            "summary": summary}


def analyze_file(path, mods, max_lines=400000):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = []
        for k, line in enumerate(f):
            if k >= max_lines:
                break
            lines.append(line)
    return analyze(lines, mods)
