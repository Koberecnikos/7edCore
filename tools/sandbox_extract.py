#!/usr/bin/env python3
"""Build app/sevenedcore/sandbox_data.json from decompiled 7 Days to Die sources.

The V3+ SandboxCode stores, per changed option, a 2-letter option id (enum SandboxOptions)
and a 1-letter index into that option's value list. Those lists live in the game's code, so
this script reads the decompiled SandboxOptionManager.cs + SandboxOptions enum:

  ilspycmd -t SandboxOptions.SandboxOptionManager Assembly-CSharp.dll > SandboxOptionManager.cs
  ilspycmd -t SandboxOptions.SandboxOptions       Assembly-CSharp.dll > SandboxOptionsEnum.cs
  python3 tools/sandbox_extract.py SandboxOptionManager.cs SandboxOptionsEnum.cs "V 3.4" [loc.json] > app/sevenedcore/sandbox_data.json

loc.json (optional): {"key": "English text"} for the "go*" keys of Data/Config/Localization.csv,
used for option labels, descriptions and value names.
"""
import json
import re
import sys


def num(s):
    s = s.strip().rstrip("fF")
    return float(s) if "." in s else int(s)


def main(mgr_path, enum_path, game, loc_path=None):
    loc = json.load(open(loc_path, encoding="utf-8")) if loc_path else {}
    src = open(mgr_path, encoding="utf-8").read()
    enum_src = open(enum_path, encoding="utf-8").read()
    body = enum_src[enum_src.index("{") + 1:enum_src.rindex("}")]
    names = [n.strip().split("=")[0].strip() for n in body.split(",") if n.strip()]
    ids = {n: i for i, n in enumerate(names) if n != "Max"}

    sets = {}
    for m in re.finditer(r'ValueSets\.Add\("(\w+)", new SandboxOptionValueSet(Float|Int|Bool)\s*\{(.*?)\n\t\t\}\);', src, re.S):
        name, typ, block = m.group(1), m.group(2).lower(), m.group(3)
        disp = re.search(r'DisplayValues = new string\[\d+\]\s*\{(.*?)\}', block, re.S)
        disp = [d.strip().strip('"') for d in disp.group(1).split(",")] if disp else []
        if typ == "bool":
            vals = [False, True]
            bv = re.search(r'BoolValues = new bool\[\d+\]\s*\{(.*?)\}', block, re.S)
            if bv:
                vals = [v.strip() == "true" for v in bv.group(1).split(",")]
        else:
            vm = re.search(r'(?:Float|Int)Values = new (?:float|int)\[\d+\]\s*\{(.*?)\}', block, re.S)
            vals = [num(v) for v in vm.group(1).split(",") if v.strip()] if vm else []
        fmt = re.search(r'DisplayFormat = "(\w+)"', block)
        sets[name] = {"type": typ, "values": vals, "display": [loc.get(d, d) for d in disp], "format": fmt.group(1) if fmt else ""}

    options = []
    for m in re.finditer(r'AddSandboxOption\(new SandboxOption(Float|Int|Boolean)\(SandboxOptions\.(\w+), "([^"]*)", "([^"]*)", "(\w+)", (?:defaultValue: )?([^,)]+)(?=(.{0,200}))', src, re.S):
        typ, name, label, cat, vset, default, tail = m.groups()
        ov = re.match(r'[^;]*?OverrideOptionName = "(\w+)"', tail)
        key = ov.group(1) if ov else "go" + name
        label = loc.get(key, label)
        desc = loc.get(key + "Desc", "")
        vs = sets.get(vset)
        if not vs or name not in ids:
            print(f"skip {name} ({vset})", file=sys.stderr)
            continue
        d = default.strip()
        dv = (d == "true") if typ == "Boolean" else num(d)
        try:
            di = vs["values"].index(dv)
        except ValueError:
            print(f"default {dv} not in {vset} for {name}", file=sys.stderr)
            di = 0
        options.append({"name": name, "id": ids[name], "label": label, "desc": desc, "category": cat, "set": vset,
                        "default": di})
    json.dump({"game": game, "version_char": "A", "sets": sets, "options": options}, sys.stdout, indent=0)
    print(f"{len(options)} options, {len(sets)} value sets", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:5])
