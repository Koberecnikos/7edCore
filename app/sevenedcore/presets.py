"""Difficulty presets, challenges and the random challenge generator.

Values use the V3 Sandbox Option names and real values (1.5 = 150 %). On V3+ servers they are
written into the SandboxCode; on older servers they are converted to the matching
serverconfig.xml properties (LEGACY). Some challenges also need a small XML modlet
(see modlets.py) - that part works on every game version."""
import random

# sandbox option -> (legacy serverconfig property, converter)
_pct = lambda v: str(round(float(v) * 100))   # noqa: E731
_int = lambda v: str(int(v))                   # noqa: E731
_bool = lambda v: "true" if v else "false"     # noqa: E731
LEGACY = {
    "XPMultiplier": ("XPMultiplier", _pct), "BlockDamage": ("BlockDamagePlayer", _pct),
    "BlockDamageAI": ("BlockDamageAI", _pct), "BlockDamageAIBM": ("BlockDamageAIBM", _pct),
    "GlobalLootCount": ("LootAbundance", _pct), "StormFreq": ("StormFreq", _pct), "JarRefund": ("JarRefund", _pct),
    "ZombieMove": ("ZombieMove", _int), "ZombieMoveNight": ("ZombieMoveNight", _int),
    "ZombieFeralMove": ("ZombieFeralMove", _int), "ZombieBMMove": ("ZombieBMMove", _int),
    "ZombieFeralSense": ("ZombieFeralSense", _int), "AISmellMode": ("AISmellMode", _int),
    "BloodMoonFrequency": ("BloodMoonFrequency", _int), "BloodMoonRange": ("BloodMoonRange", _int),
    "BloodMoonEnemyCount": ("BloodMoonEnemyCount", _int), "DayNightLength": ("DayNightLength", _int),
    "DayLightLength": ("DayLightLength", _int), "DeathPenalty": ("DeathPenalty", _int),
    "DropOnDeath": ("DropOnDeath", _int), "DropOnQuit": ("DropOnQuit", _int),
    "LootRespawnDays": ("LootRespawnDays", _int), "EnemySpawnMode": ("EnemySpawnMode", _bool),
    "QuestProgressionDailyLimit": ("QuestProgressionDailyLimit", _int),
}


def P(pid, icon, level, tier, en, cs, den, dcs, values=None, legacy=None, modlets=()):
    return {"id": pid, "icon": icon, "level": level, "tier": tier, "name": {"en": en, "cs": cs},
            "desc": {"en": den, "cs": dcs}, "values": values or {}, "legacy": legacy or {}, "modlets": list(modlets)}


PRESETS = [
    # ------------------------------------------------------------------ easy
    P("standard", "⚖️", 1, "easy", "Standard", "Standard",
      "Vanilla balance: every option the presets use goes back to default and challenge modlets are removed.", "Vanilla vyvážení: všechny volby, které presety používají, se vrátí na výchozí a challenge modlety se odeberou.",
      legacy={"GameDifficulty": "1", "EnemyDifficulty": "0"}),
    P("weekend", "🏕️", 1, "easy", "Weekend Survivor", "Víkendový přeživší",
      "Relaxed co-op: you take half damage, learn 50 % faster, find more loot, and nights crawl instead of sprint. You keep your gear on death.",
      "Pohodový co-op: poloviční zranění, o 50 % rychlejší učení, víc lootu a noci se plouží místo sprintu. Po smrti si necháš věci.",
      {"IncomingDamage": 0.5, "XPMultiplier": 1.5, "GlobalLootCount": 1.5, "DayNightLength": 90, "ZombieMoveNight": 1,
       "BloodMoonFrequency": 10, "DropOnDeath": 0}, {"GameDifficulty": "0"}),
    P("loot_goblin", "💰", 1, "easy", "Loot Goblin", "Lootovací skřet",
      "Double loot everywhere, three times as many loot bags and more treasure maps. Containers refill every 5 days.",
      "Dvojnásobný loot všude, třikrát víc lootbagů a víc map k pokladům. Kontejnery se doplní každých 5 dní.",
      {"GlobalLootCount": 2, "LootBagChance": 3, "TreasureMapChance": 2, "DukesLootCount": 2, "LootRespawnDays": 5}),
    P("bookworm", "📚", 1, "easy", "Bookworm", "Knihomol",
      "Magazines and books everywhere, and every magazine teaches twice as much. Crafting unlocks fly by.",
      "Časopisy a knihy všude a každý časopis naučí dvakrát víc. Recepty se odemykají jedna radost.",
      {"CraftingMagazinesLootCount": 3, "BookLootCount": 2, "PointsPerMagazine": 2, "XPMultiplier": 1.25}),
    P("builders", "🧱", 1, "easy", "Builder's Paradise", "Ráj stavitelů",
      "Fast crafting, double harvesting and mining, bigger stacks, and zombies chew through blocks slower.",
      "Rychlé craftění, dvojnásobná těžba a sklizeň, větší stacky a zombíci pomaleji ničí bloky.",
      {"CraftingTime": 0.25, "HarvestingOutput": 2, "MiningOutput": 2, "StackSizeMultiplier": 2,
       "BlockDamageAI": 0.5, "BlockDamageAIBM": 0.75}),
    P("party", "🎉", 1, "easy", "Party Mode", "Párty mód",
      "Big heads, tiny zombies, moon gravity and celebrations on every kill. Pure chaos, great with friends.",
      "Velké hlavy, malí zombíci, měsíční gravitace a oslavy při každém zabití. Čistý chaos, nejlepší s kamarády.",
      {"SillyBigHeads": True, "SillyTinyZombies": True, "SillyLowGravity": 0.6, "SillyCelebrate": 1, "XPMultiplier": 1.5}),
    # ------------------------------------------------------------------ medium
    P("night_terrors", "🌒", 3, "medium", "Night Terrors", "Noční můry",
      "Calm, slow days. Nights are long, and the dead sprint and track you by smell. Plan every evening.",
      "Klidné pomalé dny. Noci jsou dlouhé, mrtví sprintují a stopují tě čichem. Každý večer je potřeba naplánovat.",
      {"DayLightLength": 14, "ZombieMove": 0, "ZombieMoveNight": 4, "ZombieFeralSense": 2, "AISmellMode": 4,
       "ZombieFeralMove": 4}, {"GameDifficulty": "3"}),
    P("horde_week", "🩸", 3, "medium", "Horde Week", "Týden hord",
      "Blood moon roughly every 3 days with doubled hordes that hit blocks harder. Build fast, build smart.",
      "Krvavý měsíc zhruba každé 3 dny s dvojnásobnými hordami, které víc ničí bloky. Stav rychle a chytře.",
      {"BloodMoonFrequency": 3, "BloodMoonRange": 1, "BloodMoonEnemyCount": 16, "ZombieBMMove": 4,
       "BlockDamageAIBM": 1.5}, {"GameDifficulty": "2"}),
    P("siege", "🏰", 3, "medium", "Siege Builders", "Obléhání",
      "Zombies tear through blocks, blood moons every 5 days. Engineering and base defense are everything.",
      "Zombíci trhají bloky, krvavý měsíc každých 5 dní. Inženýrství a obrana základny jsou všechno.",
      {"BlockDamageAI": 2, "BlockDamageAIBM": 2.5, "BloodMoonFrequency": 5, "BloodMoonEnemyCount": 12,
       "BlockDamage": 1.5}, {"GameDifficulty": "2"}),
    P("short_fuse", "⏱️", 3, "medium", "Short Fuse", "Krátká rozbuška",
      "Fast weekend run: 40-minute days, 1.5× XP and a blood moon every 4 days. Progress fast or die.",
      "Rychlý víkendový běh: 40minutové dny, 1,5× XP a krvavý měsíc každé 4 dny. Postupuj rychle, nebo zemři.",
      {"DayNightLength": 40, "XPMultiplier": 1.5, "BloodMoonFrequency": 4, "BloodMoonEnemyCount": 12},
      {"GameDifficulty": "2"}),
    P("black_market", "💸", 3, "medium", "Black Market", "Černý trh",
      "Traders charge four times the price, pay a quarter for your goods and have almost nothing in stock. Everything you need, you scavenge or craft.",
      "Obchodníci chtějí čtyřnásobek, za tvé věci dají čtvrtinu a nemají skoro nic na skladě. Co potřebuješ, musíš najít nebo vyrobit.",
      {"TraderBuyPrices": 4, "TraderSellPrices": 0.25, "TraderItemAbundance": 0.25, "VendingItemAbundance": 0.25},
      modlets=["trader_prices_legacy"]),
    P("lost_knowledge", "📕", 3, "medium", "Lost Knowledge", "Ztracené vědění",
      "Magazines and books are rare - recipes come slowly. In return you get two skill points per level. Choose your perks wisely.",
      "Časopisy a knihy jsou vzácné - recepty přichází pomalu. Za to dostaneš dva skill pointy za level. Vybírej perky s rozmyslem.",
      {"CraftingMagazinesLootCount": 0.25, "BookLootCount": 0.5, "SkillPointsPerLevel": 2}),
    # ------------------------------------------------------------------ hard
    P("feral_wasteland", "☣️", 4, "hard", "Feral Wasteland", "Divoká pustina",
      "Every zombie is feral, they run by day and track you by sound and smell, hit 50 % harder. Storms are frequent.",
      "Všichni zombíci jsou ferální, přes den běhají, stopují tě podle zvuku a pachu a bijí o 50 % víc. Časté bouře.",
      {"ZombieFeralSense": 3, "ZombieMove": 2, "ZombieMoveNight": 3, "ZombieFeralMove": 4, "AISmellMode": 5,
       "StormFreq": 2, "EntityDamage": 1.5}, {"GameDifficulty": "3", "EnemyDifficulty": "1"}),
    P("lootbag_only", "🎒", 4, "hard", "Lootbag Only", "Jen lootbagy",
      "The world is picked clean: containers are empty and trees, rocks and ore give nothing. Everything comes from zombie loot bags (much more common), quests, air drops and traders.",
      "Svět je vybrakovaný: kontejnery jsou prázdné a stromy, kameny ani ruda nic nedají. Všechno je z lootbagů zombíků (padají mnohem častěji), z questů, shozů a od obchodníků.",
      {"HarvestingOutput": 0, "MiningOutput": 0, "ScrappingOutput": 0.5, "TreasureMapChance": 2},
      {"GameDifficulty": "2"}, modlets=["empty_world_loot", "more_loot_bags"]),
    P("stone_age", "🪨", 4, "hard", "Stone Age", "Doba kamenná",
      "Quality caps at level 3 for crafting, loot and traders. No legendary gear - only skill, traps and good walls.",
      "Kvalita maximálně 3 pro craft, loot i obchodníky. Žádné legendární vybavení - jen um, pasti a dobré zdi.",
      {"CraftingMaxTier": 3, "LootMaxTier": 3, "TraderMaxTier": 3, "BloodMoonEnemyCount": 10}),
    P("hardcore", "💀", 4, "hard", "Hardcore Survivor", "Hardcore přeživší",
      "Permanent death: dying resets your character and drops everything. Every fight matters.",
      "Permanentní smrt: smrt resetuje postavu a vypadne všechno. Každý souboj se počítá.",
      {"DeathPenalty": 3, "DropOnDeath": 1, "DropOnQuit": 0, "ZombieMoveNight": 3, "IncomingDamage": 1.25},
      {"GameDifficulty": "3"}),
    # ------------------------------------------------------------------ extreme
    P("insane", "🔥", 5, "extreme", "Insane Apocalypse", "Šílená apokalypsa",
      "Everything at once: double damage, feral sprinters day and night, triple hordes, heavy storms. Only for veterans.",
      "Všechno najednou: dvojnásobné zranění, ferální sprinteři ve dne i v noci, trojnásobné hordy, silné bouře. Jen pro veterány.",
      {"EntityDamage": 2, "IncomingDamage": 1.5, "ZombieMove": 3, "ZombieMoveNight": 4, "ZombieFeralMove": 4,
       "ZombieFeralSense": 3, "AISmellMode": 5, "BloodMoonEnemyCount": 24, "StormFreq": 3, "DeathPenalty": 2},
      {"GameDifficulty": "5", "EnemyDifficulty": "1"}),
]


def T(tid, score, en, cs, values=None, modlets=(), flavor=False):
    return {"id": tid, "score": score, "name": {"en": en, "cs": cs}, "values": values or {},
            "modlets": list(modlets), "flavor": flavor}


# score: negative = easier, positive = harder. flavor = changes how it plays more than how hard it is
TWISTS = [
    T("tanky", -2, "Thick skin (½ damage taken)", "Tvrdá kůže (½ zranění)", {"IncomingDamage": 0.5}),
    T("glass", 1, "Glass cannon (+50 % damage both ways)", "Skleněný kanón (+50 % zranění oběma směry)",
      {"RangedDamage": 1.5, "MeleeDamage": 1.5, "IncomingDamage": 1.5}, flavor=True),
    T("shamblers", -2, "Shamblers (zombies jog at night)", "Loudalové (zombíci v noci jen klušou)",
      {"ZombieMoveNight": 1, "ZombieBMMove": 2}),
    T("sprinters", 2, "Sprinters (run by day, nightmare by night)", "Sprinteři (ve dne běh, v noci noční můra)",
      {"ZombieMove": 2, "ZombieMoveNight": 4}),
    T("bloodhounds", 2, "Bloodhounds (smell and feral sense at night)", "Ohaři (čich a ferální smysly v noci)",
      {"AISmellMode": 4, "ZombieFeralSense": 2}),
    T("feral", 2, "Feral world (always feral, nightmare ferals)", "Ferální svět (vždy ferální)",
      {"ZombieFeralSense": 3, "ZombieFeralMove": 4}),
    T("heavy", 2, "Heavy hitters (zombies +50 % damage)", "Těžké rány (zombíci +50 % zranění)", {"EntityDamage": 1.5}),
    T("breakers", 2, "Fortress breakers (2× block damage)", "Bořiči pevností (2× poškození bloků)",
      {"BlockDamageAI": 2, "BlockDamageAIBM": 2}),
    T("headshots", 2, "Headshots only", "Jen headshoty", {"HeadshotMode": 1}, flavor=True),
    T("long_nights", 1, "Long nights (12 h daylight)", "Dlouhé noci (12 h světla)", {"DayLightLength": 12}),
    T("summer", -1, "Endless summer (20 h daylight, 90 min days)", "Nekonečné léto (20 h světla, 90min dny)",
      {"DayLightLength": 20, "DayNightLength": 90}),
    T("fast_days", 1, "Fast days (40 min)", "Rychlé dny (40 min)", {"DayNightLength": 40}, flavor=True),
    T("hordes", 2, "Horde nights (blood moon every 4 days, 12 per player)", "Noci hord (krvavý měsíc každé 4 dny)",
      {"BloodMoonFrequency": 4, "BloodMoonEnemyCount": 12}),
    T("rare_moons", -2, "Rare moons (every 14 days)", "Vzácné úplňky (každých 14 dní)", {"BloodMoonFrequency": 14}),
    T("chaos_moons", 1, "Chaos moons (every 5 days ±3)", "Chaotické úplňky (každých 5 dní ±3)",
      {"BloodMoonFrequency": 5, "BloodMoonRange": 3}, flavor=True),
    T("treasure", -1, "Treasure hunters (1.5× loot, 2× maps)", "Lovci pokladů (1,5× loot, 2× mapy)",
      {"GlobalLootCount": 1.5, "TreasureMapChance": 2}),
    T("scarce", 2, "Scarcity (½ loot, slow refill)", "Nedostatek (½ lootu, pomalé doplňování)",
      {"GlobalLootCount": 0.5, "LootRespawnDays": 20}),
    T("lootbags", 3, "Lootbag only (empty world, no harvesting)", "Jen lootbagy (prázdný svět, žádná těžba)",
      {"HarvestingOutput": 0, "MiningOutput": 0, "ScrappingOutput": 0.5}, ["empty_world_loot", "more_loot_bags"], flavor=True),
    T("black_market", 1, "Black market (4× trader prices)", "Černý trh (4× ceny u obchodníků)",
      {"TraderBuyPrices": 4, "TraderSellPrices": 0.25, "TraderItemAbundance": 0.25}, ["trader_prices_legacy"], flavor=True),
    T("generous", -1, "Generous traders (cheap, pay well)", "Štědří obchodníci (levně, dobře platí)",
      {"TraderBuyPrices": 0.75, "TraderSellPrices": 1.5}),
    T("bookworm", -1, "Bookworm (3× magazines, 2 points each)", "Knihomol (3× časopisy, 2 body)",
      {"CraftingMagazinesLootCount": 3, "PointsPerMagazine": 2}),
    T("lost_knowledge", 1, "Lost knowledge (rare magazines)", "Ztracené vědění (vzácné časopisy)",
      {"CraftingMagazinesLootCount": 0.25, "BookLootCount": 0.5}, flavor=True),
    T("fast_learner", -1, "Fast learner (1.5× XP)", "Rychlé učení (1,5× XP)", {"XPMultiplier": 1.5}),
    T("slow_learner", 1, "Slow learner (0.75× XP)", "Pomalé učení (0,75× XP)", {"XPMultiplier": 0.75}),
    T("stone_age", 2, "Stone age (quality max 3)", "Doba kamenná (kvalita max 3)",
      {"CraftingMaxTier": 3, "LootMaxTier": 3, "TraderMaxTier": 3}, flavor=True),
    T("hungry", 1, "Hungry times (1.5× hunger and thirst)", "Hladové časy (1,5× hlad a žízeň)",
      {"HungerMultiplier": 1.5, "ThirstMultiplier": 1.5}),
    T("stormy", 1, "Stormy (2× storms)", "Bouřlivo (2× bouře)", {"StormFreq": 2}, flavor=True),
    T("builder", -1, "Builder (fast crafting, 1.5× harvest)", "Stavitel (rychlé craftění, 1,5× těžba)",
      {"CraftingTime": 0.5, "HarvestingOutput": 1.5}),
    T("pack_mule", -1, "Pack mule (2× stack size)", "Mezek (2× stacky)", {"StackSizeMultiplier": 2}),
    T("no_map", 1, "Lost (no map, no compass)", "Ztracení (bez mapy a kompasu)",
      {"AllowMap": False, "AllowCompass": False}, flavor=True),
    T("permadeath", 3, "Permadeath", "Permanentní smrt", {"DeathPenalty": 3, "DropOnDeath": 1}),
    T("party", 0, "Party (big heads, tiny zombies)", "Párty (velké hlavy, malí zombíci)",
      {"SillyBigHeads": True, "SillyTinyZombies": True, "SillyCelebrate": 1}, flavor=True),
    T("moon_gravity", 0, "Moon gravity", "Měsíční gravitace", {"SillyLowGravity": 0.6}, flavor=True),
]

TIERS = {"easy": (-6, -2), "medium": (0, 3), "hard": (4, 8)}
NAMES = {"easy": ("Random · Easy", "Náhodný · Lehký", "🎲", 2), "medium": ("Random · Medium", "Náhodný · Střední", "🎲", 3),
         "hard": ("Random · Hard", "Náhodný · Těžký", "🎲", 4)}


def roll(tier, seed=None):
    """Random challenge: 3-5 non-conflicting twists, at least one 'flavor' twist, total score in the tier range."""
    if tier not in TIERS:
        raise ValueError("tier: easy, medium or hard")
    seed = int(seed) if seed not in (None, "") else random.randrange(1, 10 ** 6)
    lo, hi = TIERS[tier]
    for attempt in range(200):
        rng = random.Random(seed * 1000 + attempt)
        pool = TWISTS[:]
        rng.shuffle(pool)
        picked, keys, score = [], set(), 0
        flavors = [t for t in pool if t["flavor"]]
        first = rng.choice(flavors)
        for t in [first] + [t for t in pool if t is not first]:
            if set(t["values"]) & keys or (tier == "easy" and t["score"] >= 3) or (tier != "hard" and t["id"] == "permadeath"):
                continue
            new = score + t["score"]
            # move toward the target range, allow a step away only while we are short of twists
            if len(picked) >= 2 and not (lo <= new <= hi or abs(new - (lo + hi) / 2) < abs(score - (lo + hi) / 2)):
                continue
            picked.append(t)
            keys |= set(t["values"])
            score = new
            if len(picked) >= 3 and lo <= score <= hi and (len(picked) >= 5 or rng.random() < 0.45):
                break
        if 3 <= len(picked) <= 5 and lo <= score <= hi:
            break
    values, modlets = {}, []
    for t in picked:
        values.update(t["values"])
        modlets += [m for m in t["modlets"] if m not in modlets]
    en, cs, icon, level = NAMES[tier]
    return {"id": f"random_{tier}", "icon": icon, "level": level, "tier": tier, "seed": seed, "score": score,
            "name": {"en": f"{en} #{seed}", "cs": f"{cs} #{seed}"},
            "desc": {"en": " · ".join(t["name"]["en"] for t in picked), "cs": " · ".join(t["name"]["cs"] for t in picked)},
            "twists": [{"id": t["id"], "name": t["name"], "score": t["score"]} for t in picked],
            "values": values, "legacy": {"GameDifficulty": {"easy": "1", "medium": "2", "hard": "3"}[tier]},
            "modlets": modlets}


def managed_keys():
    """Every sandbox option any preset/twist touches - reset to default before applying another one."""
    keys = set()
    for p in PRESETS + TWISTS:
        keys |= set(p["values"])
    return keys


def public():
    """Data for the UI."""
    return {"presets": [{k: v for k, v in p.items() if k != "legacy"} for p in PRESETS],
            "tiers": list(TIERS)}
