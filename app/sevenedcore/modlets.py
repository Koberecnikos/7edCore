"""XML modlets generated for challenges (server-side XPath patches, no client install needed).

They are written to <server>/userdata/Mods/7edCore-Challenge and replaced every time a preset
is applied. legacy_only modlets are used only on servers without a SandboxCode (before V3),
where the same effect is not available as a sandbox option."""
import shutil

FOLDER = "7edCore-Challenge"

# containers that keep their loot when the world is "picked clean"
_KEEP = ("starts-with(@name,'player') or starts-with(@name,'zPack') or starts-with(@name,'vehicle') "
         "or starts-with(@name,'buriedSupplies') or contains(@name,'Writable') or @name='cntDropBag' "
         "or @name='airDrop' or @name='questSatchel' or @name='traderNPC' or @name='introBuriedSupplies' "
         "or @name='buriedTreasure' or @name='banditLoot'")

MODLETS = {
    "empty_world_loot": {
        "legacy_only": False,
        "desc": "World loot containers are empty (loot bags, air drops, quest rewards and traders keep their loot)",
        "files": {"loot.xml": f"""<configs>
	<!-- 7edCore challenge: the world is picked clean -->
	<setattribute xpath="/lootcontainers/lootcontainer[not({_KEEP})]" name="count">0</setattribute>
</configs>
"""},
    },
    "more_loot_bags": {
        "legacy_only": False,
        "desc": "Zombies drop loot bags much more often",
        "files": {"entityclasses.xml": """<configs>
	<!-- 7edCore challenge: loot bags are the main source of supplies -->
	<set xpath="/entity_classes/entity_class/property[@name='LootDropProb']/@value">0.3</set>
</configs>
"""},
    },
    "trader_prices_legacy": {
        "legacy_only": True,
        "desc": "Traders charge 4x and pay 1/4 (pre-V3 servers)",
        "files": {"traders.xml": """<configs>
	<!-- 7edCore challenge: black market prices -->
	<set xpath="/traders/@buy_markup">12</set>
	<set xpath="/traders/@sell_markdown">0.05</set>
	<set xpath="/traders/trader_info[@is_vending='true']/@override_buy_markup">12</set>
</configs>
"""},
    },
}

MODINFO = """<?xml version="1.0" encoding="UTF-8" ?>
<xml>
	<Name value="7edCore-Challenge" />
	<DisplayName value="7edCore challenge" />
	<Description value="{desc}" />
	<Author value="7edCore" />
	<Version value="1.0" />
	<Website value="https://github.com/Koberecnikos/7edCore" />
</xml>
"""


def applicable(ids, sandbox_mode):
    return [m for m in ids if m in MODLETS and not (sandbox_mode and MODLETS[m]["legacy_only"])]


def write(mods_dir, ids):
    """(Re)create the challenge modlet; remove it when no modlet is needed. Returns the used ids."""
    target = mods_dir / FOLDER
    for d in (target, mods_dir.parent / "Mods_disabled" / FOLDER):
        if d.exists():
            shutil.rmtree(d)
    if not ids:
        return []
    files = {}
    for m in ids:
        for name, body in MODLETS[m]["files"].items():
            if name in files:                                   # merge patches into one file per config
                body = files[name].replace("</configs>\n", "") + body.replace("<configs>\n", "", 1)
            files[name] = body
    (target / "Config").mkdir(parents=True)
    desc = "; ".join(MODLETS[m]["desc"] for m in ids).replace('"', "'")
    (target / "ModInfo.xml").write_text(MODINFO.format(desc=desc), encoding="utf-8")
    for name, body in files.items():
        (target / "Config" / name).write_text(body, encoding="utf-8")
    return ids
