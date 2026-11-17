"""Static mod compatibility check against an installed game version - without starting the server.

Code mods (DLL): every type / method / field a mod uses from the game's Assembly-CSharp is looked up
in the game's own Assembly-CSharp.dll, and every Harmony patch target ([HarmonyPatch(typeof(X), "M")])
is checked. Something missing = the mod was built for another game version and will fail or misbehave.

XML mods: every XPath patch in Config/*.xml is evaluated against the game's own Data/Config XML.
A patch that matches nothing is either outdated or meant for content another mod adds.
"""
import json
import os
import re
import struct
from pathlib import Path

from .util import PANEL_DIR, load_json, save_json

GAME_ASSEMBLIES = ("Assembly-CSharp", "Assembly-CSharp-firstpass")
CACHE_DIR = PANEL_DIR / "modcheck-cache"
METHOD_TYPES = {1: "get_", 2: "set_"}          # HarmonyLib.MethodType Getter / Setter


def _s(x):
    if x is None:
        return ""
    return str(getattr(x, "value", x) or "")


def _blob(x):
    v = getattr(x, "value", x)
    return bytes(v) if v is not None else b""


# ------------------------------------------------------------------ game assembly index
def _index_assembly(path):
    import dnfile
    pe = dnfile.dnPE(str(path), fast_load=False)
    t = pe.net.mdtables
    tds = list(t.TypeDef or [])
    enclosing = {}
    for n in t.NestedClass or []:
        enclosing[n.NestedClass.row_index] = n.EnclosingClass.row_index

    def fullname(i, depth=0):
        r = tds[i - 1]
        name = _s(r.TypeName)
        if i in enclosing and depth < 10:
            return fullname(enclosing[i], depth + 1) + "/" + name
        ns = _s(r.TypeNamespace)
        return f"{ns}.{name}" if ns else name

    props = {}
    for pm in t.PropertyMap or []:
        props[pm.Parent.row_index] = [_s(p.row.Name) for p in pm.PropertyList]
    types = {}
    for i, r in enumerate(tds, 1):
        base = None
        ext = r.Extends
        if ext is not None and ext.table is not None and ext.row_index:
            if ext.table.name == "TypeDef":
                base = ("def", ext.row_index)
            elif ext.table.name == "TypeRef":
                tr = t.TypeRef[ext.row_index - 1]
                base = ("ref", f"{_s(tr.TypeNamespace)}.{_s(tr.TypeName)}".lstrip("."))
        types[i] = {"name": fullname(i), "base": base,
                    "m": sorted({_s(m.row.Name) for m in r.MethodList if m.row}),
                    "f": sorted({_s(f.row.Name) for f in r.FieldList if f.row}),
                    "p": props.get(i, [])}
    out = {}
    for i, ty in types.items():
        b = ty["base"]
        out[ty["name"]] = {"m": ty["m"], "f": ty["f"], "p": ty["p"],
                           "base": types[b[1]]["name"] if b and b[0] == "def" and b[1] in types else (b[1] if b else None)}
    return out


def game_index(server_dir: Path):
    """{assembly name: {type full name: {"m": [...], "f": [...], "p": [...], "base": name}}}, cached per file."""
    managed = Path(server_dir) / "7DaysToDieServer_Data" / "Managed"
    res = {}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for an in GAME_ASSEMBLIES:
        f = managed / f"{an}.dll"
        if not f.exists():
            continue
        st = f.stat()
        import hashlib
        tag = hashlib.sha1(str(f.resolve()).encode()).hexdigest()[:10]
        key = f"{an}_{tag}_{st.st_size}_{st.st_mtime_ns}.json"
        cached = load_json(CACHE_DIR / key, None)
        if cached is None:
            cached = _index_assembly(f)
            for old in CACHE_DIR.glob(f"{an}_{tag}_*.json"):
                old.unlink()
            save_json(CACHE_DIR / key, cached)
        res[an] = cached
    return res, managed


def _has_member(index, tname, member, kind, depth=0):
    """True / False, or None when the member could be inherited from outside the game assembly (unknown)."""
    ty = index.get(tname)
    if ty is None or depth > 30:
        return None
    pool = ty["f"] if kind == "f" else ty["m"]
    if member in pool:
        return True
    if kind == "m" and member.startswith(("get_", "set_")) and member[4:] in ty["p"]:
        return True
    if ty["base"] and ty["base"] in index:
        return _has_member(index, ty["base"], member, kind, depth + 1)
    return None if ty["base"] and ty["base"] not in ("System.Object", "Object") else False


# ------------------------------------------------------------------ custom attribute blobs
def _read_compressed(b, i):
    x = b[i]
    if x & 0x80 == 0:
        return x, i + 1
    if x & 0xC0 == 0x80:
        return ((x & 0x3F) << 8) | b[i + 1], i + 2
    return ((x & 0x1F) << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3], i + 4


def _read_serstring(b, i):
    if b[i] == 0xFF:
        return None, i + 1
    n, i = _read_compressed(b, i)
    return b[i:i + n].decode("utf-8", "replace"), i + n


def _ctor_params(sig):
    """Element types of a constructor signature (only what HarmonyPatch uses)."""
    try:
        i = 1
        n, i = _read_compressed(sig, i)
        i += 1                                   # return type (void)
        out = []
        for _ in range(n):
            et = sig[i]
            i += 1
            if et == 0x1D:                       # SZARRAY of ...
                inner = sig[i]
                i += 1
                if inner in (0x12, 0x11):
                    _v, i = _read_compressed(sig, i)
                out.append(("array", inner))
            elif et in (0x12, 0x11):             # class / valuetype token
                tok, i = _read_compressed(sig, i)
                out.append(("class" if et == 0x12 else "enum", tok))
            else:
                out.append(("prim", et))
        return out
    except IndexError:
        return None


def _harmony_args(blob, params):
    """-> (type name or None, method name or None, MethodType or None)"""
    if not blob.startswith(b"\x01\x00") or params is None:
        return None
    i, tname, mname, mtype = 2, None, None, None
    try:
        for kind, et in params:
            if kind == "class":                  # System.Type -> serialized type name
                v, i = _read_serstring(blob, i)
                tname = tname or v
            elif kind == "prim" and et == 0x0E:  # string
                v, i = _read_serstring(blob, i)
                mname = mname or v
            elif kind == "enum":                 # MethodType / ArgumentType: int32
                v = struct.unpack_from("<i", blob, i)[0]
                i += 4
                mtype = v if mtype is None else mtype
            elif kind == "array":
                n = struct.unpack_from("<I", blob, i)[0]
                i += 4
                if n != 0xFFFFFFFF:
                    for _ in range(n):
                        if et in (0x0E, 0x12):
                            _v, i = _read_serstring(blob, i)
                        else:
                            i += 4
            else:
                return None
    except (IndexError, struct.error):
        return None
    return tname, mname, mtype


def _clean_type(name):
    """'Outer+Inner, Assembly-CSharp, Version=..' -> ('Outer/Inner', 'Assembly-CSharp')"""
    if not name:
        return None, None
    parts = [p.strip() for p in name.split(",")]
    return parts[0].replace("+", "/"), (parts[1] if len(parts) > 1 else None)


# ------------------------------------------------------------------ one DLL
def check_dll(path, gidx, managed, mod_dirs=()):
    import dnfile
    issues = []
    try:
        pe = dnfile.dnPE(str(path), fast_load=False)
    except Exception as e:
        return [{"severity": "warning", "kind": "unreadable", "text": f"{Path(path).name}: not a readable .NET assembly ({e})"}]
    if not getattr(pe, "net", None) or not pe.net.mdtables:
        return []
    t = pe.net.mdtables
    arefs = [_s(r.Name) for r in t.AssemblyRef or []]
    # referenced assemblies that exist nowhere
    game_mods = managed.parent.parent / "Mods"              # built-in mods of the game (TFP_Harmony ...)
    local = {p.stem for d in list(mod_dirs) + ([game_mods] if game_mods.is_dir() else []) for p in Path(d).rglob("*.dll")} | {Path(path).stem}
    for an in arefs:
        if an in local or an in ("mscorlib", "netstandard") or an.startswith(("System", "Microsoft.", "Unity", "Mono.")):
            continue
        if not (managed / f"{an}.dll").exists():
                issues.append({"severity": "error", "kind": "missing_dll",
                               "text": f"{Path(path).name} needs {an}.dll, which is neither in the game nor in any mod"})
    trs = list(t.TypeRef or [])

    def tr_name(i, depth=0):
        r = trs[i - 1]
        rs = r.ResolutionScope
        if rs is not None and rs.table is not None and rs.table.name == "TypeRef" and depth < 10:
            outer, asm = tr_name(rs.row_index, depth + 1)
            return f"{outer}/{_s(r.TypeName)}", asm
        asm = arefs[rs.row_index - 1] if rs is not None and rs.table is not None and rs.table.name == "AssemblyRef" and 0 < rs.row_index <= len(arefs) else None
        ns = _s(r.TypeNamespace)
        return (f"{ns}.{_s(r.TypeName)}" if ns else _s(r.TypeName)), asm

    missing_types = {}
    for i in range(1, len(trs) + 1):
        name, asm = tr_name(i)
        if asm in gidx and name not in gidx[asm]:
            missing_types[name] = asm
    for name in sorted(missing_types):
        issues.append({"severity": "error", "kind": "missing_type", "text": f"uses game type {name}, which does not exist in this game version"})
    seen = set()
    for r in t.MemberRef or []:
        c = r.Class
        if c is None or c.table is None or c.table.name != "TypeRef":
            continue
        tname, asm = tr_name(c.row_index)
        if asm not in gidx or tname in missing_types:
            continue
        member = _s(r.Name)
        if member in (".ctor", ".cctor"):
            continue
        sig = _blob(r.Signature)
        kind = "f" if sig[:1] == b"\x06" else "m"
        if (tname, member) in seen:
            continue
        seen.add((tname, member))
        if _has_member(gidx[asm], tname, member, kind) is False:
            what = "field" if kind == "f" else "method"
            issues.append({"severity": "error", "kind": "missing_member",
                           "text": f"uses {tname}.{member} ({what}), which does not exist in this game version"})
    # Harmony patch targets
    tds = list(t.TypeDef or [])
    mdefs = list(t.MethodDef or [])
    owner_of_method = {}
    for ti, td in enumerate(tds, 1):
        for m in td.MethodList:
            owner_of_method[m.row_index] = ti
    patches = {}
    for ca in t.CustomAttribute or []:
        ct = ca.Type
        if ct is None or ct.table is None or ct.table.name != "MemberRef":
            continue
        mr = t.MemberRef[ct.row_index - 1]
        cls = mr.Class
        if cls is None or cls.table is None or cls.table.name != "TypeRef":
            continue
        an, _asm = tr_name(cls.row_index)
        if an != "HarmonyLib.HarmonyPatch":
            continue
        args = _harmony_args(_blob(ca.Value), _ctor_params(_blob(mr.Signature)))
        if not args:
            continue
        p = ca.Parent
        if p is None or p.table is None:
            continue
        cls_i = p.row_index if p.table.name == "TypeDef" else owner_of_method.get(p.row_index) if p.table.name == "MethodDef" else None
        if not cls_i:
            continue
        cur = patches.setdefault(cls_i, {"type": None, "method": None, "mtype": None})
        cur["type"] = cur["type"] or args[0]
        cur["method"] = cur["method"] or args[1]
        cur["mtype"] = cur["mtype"] if cur["mtype"] is not None else args[2]
    for cls_i, pt in patches.items():
        tname, asm = _clean_type(pt["type"])
        if not tname:
            continue
        idx = gidx.get(asm or "Assembly-CSharp") or (gidx.get("Assembly-CSharp") if asm is None else None)
        if idx is None:
            continue
        pname = _s(tds[cls_i - 1].TypeName) if cls_i <= len(tds) else "?"
        if tname not in idx:
            issues.append({"severity": "error", "kind": "harmony_target",
                           "text": f"Harmony patch {pname} targets type {tname}, which does not exist in this game version"})
            continue
        m = pt["method"]
        if not m or pt["mtype"] in (3, 4, 5):            # constructor / enumerator patches: not checked
            continue
        mm = METHOD_TYPES.get(pt["mtype"], "") + m
        if _has_member(idx, tname, mm, "m") is False:
            issues.append({"severity": "error", "kind": "harmony_target",
                           "text": f"Harmony patch {pname} targets {tname}.{mm}, which does not exist in this game version"})
    return issues


# ------------------------------------------------------------------ XML patches
XML_OPS = ("set", "setattribute", "append", "prepend", "insertafter", "insertbefore", "remove", "removeattribute", "csv")


def _xml_docs(server_dir):
    return Path(server_dir) / "Data" / "Config"


def check_xml(mod_dir, server_dir, other_mods_text, cache):
    from lxml import etree
    issues = []
    cfg = Path(mod_dir) / "Config"
    vanilla = _xml_docs(server_dir)
    if not cfg.is_dir():
        return issues
    for f in sorted(cfg.rglob("*.xml")):
        rel = f.relative_to(cfg)
        target = vanilla / rel
        if not target.exists():
            continue                                     # the mod's own new file
        try:
            root = etree.parse(str(f), etree.XMLParser(recover=False, remove_comments=True)).getroot()
        except etree.XMLSyntaxError as e:
            issues.append({"severity": "error", "kind": "xml_invalid", "text": f"Config/{rel}: invalid XML ({e})"})
            continue
        key = str(rel)
        if key not in cache:
            try:
                cache[key] = etree.parse(str(target), etree.XMLParser(remove_comments=True))
            except etree.XMLSyntaxError:
                cache[key] = None
        doc = cache[key]
        if doc is None:
            continue
        for el in root.iter():
            if not isinstance(el.tag, str) or el.tag.lower() not in XML_OPS:
                continue
            if any(isinstance(a.tag, str) and a.tag.lower() in ("conditional", "if", "else") for a in el.iterancestors()):
                continue                                 # depends on other mods / settings
            xp = el.get("xpath")
            if not xp:
                continue
            try:
                found = doc.xpath(xp)
            except etree.XPathError:
                issues.append({"severity": "warning", "kind": "xpath_invalid", "text": f"Config/{rel}: XPath not understood: {xp[:160]}"})
                continue
            if found not in ([], None, False):
                continue
            names = re.findall(r"@name\s*=\s*['\"]([^'\"]+)['\"]", xp)
            owners = sorted({m for m, txt in other_mods_text.items() for n in names if f'"{n}"' in txt or f"'{n}'" in txt})
            if owners:
                issues.append({"severity": "info", "kind": "xpath_other_mod",
                               "text": f"Config/{rel}: <{el.tag}> changes content added by {', '.join(owners)} (fine while that mod is installed)"})
            else:
                issues.append({"severity": "warning", "kind": "xpath_nomatch",
                               "text": f"Config/{rel}: <{el.tag} xpath=\"{xp[:160]}\"> matches nothing in this game version - outdated patch"})
    return issues


# ------------------------------------------------------------------ whole mod set
def check_mods(mod_dirs, server_dir):
    """mod_dirs: {folder: Path}. -> {"game_dlls": bool, "mods": {folder: [issues]}}"""
    try:
        gidx, managed = game_index(server_dir)
    except ImportError:
        gidx, managed = {}, Path(server_dir)
    texts = {}
    for name, d in mod_dirs.items():
        parts = []
        for f in Path(d).rglob("*.xml"):
            try:
                parts.append(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        texts[name] = "\n".join(parts)
    out, cache = {}, {}
    for name, d in mod_dirs.items():
        issues = []
        if gidx:
            for dll in sorted(Path(d).rglob("*.dll")):
                if dll.name.lower() in ("0harmony.dll",):
                    continue
                for it in check_dll(dll, gidx, managed, mod_dirs.values()):
                    it["file"] = str(dll.relative_to(d))
                    issues.append(it)
        try:
            issues += check_xml(d, server_dir, {k: v for k, v in texts.items() if k != name}, cache)
        except ImportError:
            pass
        out[name] = issues
    return {"game_dlls": bool(gidx), "mods": out}
