"""Bypass a mod's own game-version gate - only that, nothing else.

Some mods refuse to start on a game version their author has not listed yet:

    if (!supported) throw new NotSupportedException("This update supports 7D2D 3.1, 3.2 and 3.3 ...");

In IL that is `ldstr "<message>"; newobj <SomeException>::.ctor(string); throw` (11 bytes). Replacing
exactly those bytes with `nop` lets the code continue as if the version were supported. Nothing else
in the file changes, the offsets stay the same, and the original is kept next to it (*.orig).
Whether the mod then really works depends on what the new game version changed - check it with the
compatibility check first and look at the log after the next start.
"""
import re
import shutil
from pathlib import Path

GATE_EXCEPTIONS = {"NotSupportedException", "InvalidOperationException", "Exception", "PlatformNotSupportedException",
                   "ApplicationException", "NotImplementedException"}
VERSION_WORDS = re.compile(r"(version|supports?|supported|compatib|requires? (7d2d|7 days|the game|game version)|"
                           r"only (works|for)|\b[vV]?\d+\.\d+\b)", re.I)


def _user_string(us_data, idx):
    if idx <= 0 or idx >= len(us_data):
        return None
    n = us_data[idx]
    if n & 0x80 == 0:
        ln, i = n, idx + 1
    elif n & 0xC0 == 0x80:
        ln, i = ((n & 0x3F) << 8) | us_data[idx + 1], idx + 2
    else:
        ln, i = ((n & 0x1F) << 24) | (us_data[idx + 1] << 16) | (us_data[idx + 2] << 8) | us_data[idx + 3], idx + 4
    return us_data[i:i + max(ln - 1, 0)].decode("utf-16-le", "replace")


def _ctor_class(t, token):
    table, rid = token >> 24, token & 0xFFFFFF
    try:
        if table == 0x0A:                                   # MemberRef
            c = t.MemberRef[rid - 1].Class
            if c is not None and c.table is not None and c.table.name == "TypeRef":
                return str(getattr(t.TypeRef[c.row_index - 1].TypeName, "value", t.TypeRef[c.row_index - 1].TypeName))
        if table == 0x06:                                   # MethodDef: the mod's own exception type
            for td in t.TypeDef or []:
                if any(m.row_index == rid for m in td.MethodList):
                    return str(getattr(td.TypeName, "value", td.TypeName))
    except (IndexError, AttributeError):
        pass
    return None


def _method_bodies(pe, t):
    """(method name, file offset of the code, code size) for every method with IL."""
    for m in t.MethodDef or []:
        if not m.Rva:
            continue
        try:
            off = pe.get_offset_from_rva(m.Rva)
        except Exception:
            continue
        data = pe.__data__
        h = data[off]
        if h & 0x3 == 0x2:                                  # tiny header
            yield str(m.Name), off + 1, h >> 2
        elif h & 0x3 == 0x3:                                # fat header
            size = int.from_bytes(data[off + 4:off + 8], "little")
            hdr = (int.from_bytes(data[off:off + 2], "little") >> 12) * 4
            yield str(m.Name), off + hdr, size


def find_gates(path):
    """Version gates in one assembly: [{"offset", "method", "message", "exception"}]."""
    import dnfile
    try:
        pe = dnfile.dnPE(str(path), fast_load=False)
    except Exception:
        return []
    if not getattr(pe, "net", None) or not pe.net.mdtables:
        return []
    t = pe.net.mdtables
    us = pe.net.user_strings
    us_data = bytes(getattr(us, "__data__", b"") or b"")
    data = pe.__data__
    found = []
    for name, start, size in _method_bodies(pe, t):
        code = data[start:start + size]
        for mt in re.finditer(rb"\x72(.{3})\x70\x73(.{3})([\x0a\x06])\x7a", code, re.S):
            sidx = int.from_bytes(mt.group(1), "little")
            msg = _user_string(us_data, sidx)
            exc = _ctor_class(t, (mt.group(3)[0] << 24) | int.from_bytes(mt.group(2), "little"))
            if not msg or exc not in GATE_EXCEPTIONS or not VERSION_WORDS.search(msg):
                continue
            found.append({"offset": start + mt.start(), "method": name, "message": msg, "exception": exc})
    return found


def scan_mod(mod_dir):
    """{relative dll path: [gates]} for the mod's loader DLLs (top two folder levels)."""
    out = {}
    d = Path(mod_dir)
    for f in sorted(d.rglob("*.dll")):
        if len(f.relative_to(d).parts) > 3 or f.name.lower() == "0harmony.dll":
            continue
        g = find_gates(f)
        if g:
            out[str(f.relative_to(d))] = g
    return out


def apply(mod_dir):
    """Neutralise every version gate found. Returns {file: [messages]}; originals saved as *.orig."""
    d = Path(mod_dir)
    done = {}
    for rel, gates in scan_mod(d).items():
        f = d / rel
        orig = f.with_name(f.name + ".orig")
        if not orig.exists():
            shutil.copy2(f, orig)
        raw = bytearray(f.read_bytes())
        for g in gates:
            o = g["offset"]
            if raw[o] == 0x72 and raw[o + 5] == 0x73 and raw[o + 10] == 0x7A:
                raw[o:o + 11] = b"\x00" * 11
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_bytes(bytes(raw))
        tmp.replace(f)
        done[rel] = [g["message"] for g in gates]
    return done


def revert(mod_dir):
    d = Path(mod_dir)
    restored = []
    for orig in d.rglob("*.dll.orig"):
        orig.replace(orig.with_name(orig.name[:-5]))
        restored.append(str(orig.relative_to(d))[:-5])
    return restored
