"""Game version parsing and save compatibility rules.

7 Days to Die versions look like "Alpha 21.2", "V 1.4", "V 3.4.0" (logs) or
"alpha21.2", "v2.6", "v3.4.0" (Steam branches). Saves are tied to the game version:
  * same version (only build/hotfix differs)  -> compatible
  * newer minor version of the same major      -> usually works, back up first
  * different major (A21 -> V1, V2 -> V3)      -> not compatible, start a new world
  * older version than the save                -> downgrade, not supported
"""
import re

_V = re.compile(r"\b[Vv]\s?(\d+)\.(\d+)(?:\.(\d+))?")
_A = re.compile(r"\b(?:[Aa]lpha|A)\s?(\d{1,2})(?:\.(\d+))?\b")
_VWORD = re.compile(r"\bVersion\s+(\d+)\.(\d+)(?:\.(\d+))?")              # Steam branch description
_VLOOSE = re.compile(r"\b[Vv]\s?(\d{1,2})(?:\.(\d+))?(?:\.(\d+))?\b")   # mod notes: "V2", "v1.4", "V 3.4.0"


def parse(text):
    """Return the first version found in text as dict, or None."""
    if not text:
        return None
    s = str(text)
    m = _V.search(s) or _VWORD.search(s)
    if m:
        return _mk("V", int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    m = _A.search(s)
    if m:
        return _mk("A", int(m.group(1)), int(m.group(2) or 0), 0)
    return None


def find_all(text):
    """All distinct versions mentioned in a text (used for mod release notes)."""
    out, seen = [], set()
    s = str(text or "")
    for m in _VLOOSE.finditer(s):
        v = _mk("V", int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))
        if v["label"] not in seen:
            seen.add(v["label"])
            out.append(v)
    for m in _A.finditer(s):
        v = _mk("A", int(m.group(1)), int(m.group(2) or 0), 0)
        if v["label"] not in seen:
            seen.add(v["label"])
            out.append(v)
    return out


def _mk(kind, major, minor, patch):
    if kind == "V":
        label = f"V {major}.{minor}" + (f".{patch}" if patch else "")
    else:
        label = f"Alpha {major}.{minor}"
    return {"kind": kind, "major": major, "minor": minor, "patch": patch, "label": label,
            "family": f"{'V' if kind == 'V' else 'A'}{major}"}


def key(v):
    return (1 if v["kind"] == "V" else 0, v["major"], v["minor"], v["patch"])


def compat(save_v, game_v):
    """Compatibility of a save made with save_v when started on game_v.
    level: same | newer_minor | major | downgrade | unknown"""
    if not save_v or not game_v:
        return {"level": "unknown"}
    a, b = key(save_v), key(game_v)
    if a == b or (a[:3] == b[:3] and b[3] > a[3]):      # identical or hotfix of the same version
        return {"level": "same"}
    if b < a:
        return {"level": "downgrade"}
    if save_v["family"] == game_v["family"]:
        return {"level": "newer_minor"}
    return {"level": "major"}


def update_kind(cur_v, new_v):
    """How big is a game update: none | patch | minor | major | unknown."""
    if not cur_v or not new_v:
        return "unknown"
    if key(cur_v) == key(new_v):
        return "patch"            # same version, newer build (hotfix)
    if key(new_v) < key(cur_v):
        return "major"            # branch went backwards - treat as dangerous
    if cur_v["family"] == new_v["family"]:
        return "minor"
    return "major"


def mod_compat(mod_mentions, game_v):
    """Is a mod release (versions mentioned in its tag/notes) made for game_v?
    yes | no | unknown"""
    if not game_v:
        return "unknown"
    if not mod_mentions:
        return "unknown"
    if any(m["family"] == game_v["family"] for m in mod_mentions):
        return "yes"
    return "no"
