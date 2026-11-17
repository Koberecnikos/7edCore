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


def _dll_type_names(path):
    """Namespaces and top-level type names defined in a DLL (empty if it cannot be read)."""
    try:
        import dnfile
        pe = dnfile.dnPE(str(path), fast_load=False)
        out = set()
        for r in pe.net.mdtables.TypeDef or []:
            ns, nm = str(getattr(r.TypeNamespace, "value", r.TypeNamespace) or ""), str(getattr(r.TypeName, "value", r.TypeName) or "")
            if nm.startswith("<"):
                continue
            out.add(f"{ns}.{nm}" if ns else nm)
            if ns:
                out.add(ns)
        return out
    except Exception:
        return set()


# how bad a problem is for the game (not just for the mod)
IMPACT = {"xml_failed": "breaks", "missing_dependency": "breaks", "runtime_spam": "lag",
          "code_failed": "feature", "types_failed": "feature", "harmony_target": "feature", "missing_class": "feature",
          "runtime_errors": "feature", "patch_not_applied": "minor", "log": "minor"}
SEVERITY = {"breaks": "error", "lag": "error", "feature": "warning", "minor": "info"}
RUNTIME_SPAM = 20                                 # errors from one mod while the game runs -> likely lag


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
        self.code = {}                            # top-level type / namespace names in the mod's DLLs -> folder
        for m in mods:
            for dll in Path(m["path"]).rglob("*.dll"):
                if dll.name.lower() == "0harmony.dll":
                    continue
                for n in _dll_type_names(dll):
                    self.code.setdefault(n, m["folder"])

    def from_frame(self, frame):
        """'DrokkStoragePatches+X.Prefix (...)' / 'Foo.Bar:Baz(...)' -> mod folder"""
        name = re.split(r"[\s:(]", frame.strip(), 1)[0]
        parts = re.split(r"[.+/]", name)
        for k in range(len(parts), 0, -1):
            f = self.code.get(".".join(parts[:k]))
            if f:
                return f
        return self.by.get(parts[0].lower()) if parts and len(parts[0]) > 3 else None   # namespace = mod name

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
        imp = IMPACT.get(kind, "minor" if sev != "error" else "feature")
        lst.append({"severity": SEVERITY[imp], "impact": imp, "kind": kind, "text": text, "detail": detail, "count": 1})

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

    harmony_user, started = None, False
    runtime = {}                                  # folder -> [count, first message]

    def frame_mod(i):
        for j in range(i + 1, min(n, i + 14)):
            t = L[j]
            if t.startswith("EXC "):
                continue                          # ERR line + its exception: the stack trace follows
            if re.match(r"(INF|ERR|WRN) ", t):
                return None                       # next log entry: this message had no stack trace
            fr = t.strip()[3:] if t.strip().startswith("at ") else (t if re.match(r"^[\w.+<>`]+:[\w<>.`]+\(", t) else None)
            if fr:
                f = mm.from_frame(fr)
                if f:
                    return f
        return None

    prev_entry = ""
    for i, s in enumerate(L):
        if not s:
            continue
        if "StartGame done" in s:
            started = True
        entry = s[:4] if re.match(r"(INF|ERR|WRN|EXC) ", s) else None
        after_err, prev_entry = prev_entry == "ERR ", (entry or prev_entry)
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
        if s.startswith("EXC ") and after_err:
            continue                              # the reason of the ERR line just before it
        if re.match(r"(ERR|EXC) |\w*Exception", s) and not NOISE.match(s.replace("EXC ", "", 1)):
            f = frame_mod(i)
            if f:
                if started:
                    r = runtime.setdefault(f, [0, s[:240]])
                    r[0] += 1
                else:
                    add(f, "error", "log", re.sub(r"^(ERR|EXC) ", "", s[:240]))
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
    for f, (cnt, first) in runtime.items():
        if cnt >= RUNTIME_SPAM:
            add(f, "error", "runtime_spam", f"Throws errors over and over while the game runs ({cnt}x in this log) - this costs server performance (lag)", first)
        else:
            add(f, "error", "runtime_errors", f"Errors while the game runs ({cnt}x) - something in the mod fails, usually only that feature", first)
        per_mod[f][-1]["count"] = cnt
    # a mod whose code failed AND whose XML broke a game file: say so in one place
    for f, lst in per_mod.items():
        if any(i["kind"] == "xml_failed" for i in lst):
            for it in lst:
                if it["kind"] == "code_failed":
                    it["detail"] = (it["detail"] + " | " if it["detail"] else "") + "its XML still uses the code, so game files fail to load"
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
    order = {"breaks": 0, "lag": 1, "feature": 2, "minor": 3}
    for f, lst in per_mod.items():
        lst.sort(key=lambda it: order.get(it.get("impact"), 4))
    worst = {f: min((order.get(i.get("impact"), 4) for i in l), default=4) for f, l in per_mod.items()}
    summary = {"mods_error": sorted(f for f, w in worst.items() if w <= 1),        # breaks the game / lag
               "mods_warning": sorted(f for f, w in worst.items() if w == 2),      # part of the mod does not work
               "mods_minor": sorted(f for f, w in worst.items() if w == 3),
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
