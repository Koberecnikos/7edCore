"""V3+ Sandbox Options: decode / encode the serverconfig SandboxCode.

Code format (from the game's SandboxOptionManager): a version letter ('A') followed by one
3-letter group per option that differs from its default: two letters for the option id
(enum SandboxOptions, id = 26*a + b) and one letter for the index into that option's value
list. Value lists come from sandbox_data.json (see tools/sandbox_extract.py)."""
import json
from pathlib import Path

DATA = json.loads((Path(__file__).with_name("sandbox_data.json")).read_text())
SETS = DATA["sets"]
OPTIONS = {o["name"]: o for o in DATA["options"]}
BY_ID = {o["id"]: o for o in DATA["options"]}
VERSION = DATA.get("version_char", "A")


def values(name):
    return SETS[OPTIONS[name]["set"]]["values"]


def value_label(name, i):
    s = SETS[OPTIONS[name]["set"]]
    v = s["values"][i]
    disp = s["display"]
    if len(disp) == len(s["values"]) or i < len(disp):
        d = disp[i]
        d = {"none": "Off", "lblAll": "All", "xuiDefault": "Default", "xuiDurability": "Durability",
             "xuiMaxDurability": "Max durability", "xuiBoth": "Both", "lblContextActionRecipes": "Recipes",
             "xuiOptionsVideoTexQualityFull": "Full"}.get(d, d)
        if "{0}" in d:
            d = d.replace("{0}", f"{v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
        return d
    tpl = next((d for d in disp if "{0}" in d), None)
    if tpl and isinstance(v, (int, float)) and not isinstance(v, bool):
        if tpl.endswith(" Day") and v != 1:
            tpl += "s"
        return tpl.replace("{0}", f"{v:g}")
    if s["format"] == "goPercent" and isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{round(v * 100)}%"
    return str(v)


def decode(code):
    """SandboxCode -> {option name: value index} (only options present in the code)."""
    out = {}
    if not code or code[0] != VERSION:
        return out
    body = code[1:]
    for k in range(0, len(body) - 2, 3):
        oid = (ord(body[k]) - 65) * 26 + (ord(body[k + 1]) - 65)
        idx = ord(body[k + 2]) - 65
        o = BY_ID.get(oid)
        if o and 0 <= idx < len(SETS[o["set"]]["values"]):
            out[o["name"]] = idx
    return out


def encode(indexes):
    """{option name: value index} -> SandboxCode (defaults left out, sorted by id)."""
    parts = []
    for name, idx in sorted(indexes.items(), key=lambda kv: OPTIONS[kv[0]]["id"]):
        o = OPTIONS[name]
        if idx == o["default"]:
            continue
        oid = o["id"]
        parts.append(chr(65 + oid // 26) + chr(65 + oid % 26) + chr(65 + idx % 26))
    return VERSION + "".join(parts)


def full(code):
    """All options with the current index (defaults filled in)."""
    cur = decode(code)
    return {n: cur.get(n, o["default"]) for n, o in OPTIONS.items()}


def index_for(name, value):
    """Index of the value closest to `value` (exact for bools / ints)."""
    vals = values(name)
    if isinstance(value, bool) or isinstance(vals[0], bool):
        return vals.index(bool(value))
    if value in vals:
        return vals.index(value)
    nums = [(abs(float(v) - float(value)), i) for i, v in enumerate(vals) if not isinstance(v, bool)]
    return min(nums)[1]


def catalog():
    return {"game": DATA["game"], "options": [
        {"name": o["name"], "label": o["label"], "desc": o["desc"].replace("\\n", " ").replace("  ", " "), "category": o["category"], "default": o["default"],
         "values": [value_label(o["name"], i) for i in range(len(SETS[o["set"]]["values"]))]}
        for o in DATA["options"]]}
