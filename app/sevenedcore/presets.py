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


def OFFICIAL(code):
    """Values of an official sandbox preset code (decoded with the game's option tables)."""
    from . import sandbox
    return {n: sandbox.values(n)[i] for n, i in sandbox.decode(code).items()}


def D(pid, icon, level, tier, group, en, cs, den, dcs, values=None, legacy=None, modlets=()):
    p = P(pid, icon, level, tier, en, cs, den, dcs, values, legacy, modlets)
    p["group"] = group
    return p


PRESETS = [
    # ------------------------------------------------------------------ game difficulty (exact codes from the game)
    D("standard", "⚖️", 1, "easy", "difficulty", "Standard", "Standard",
      "Vanilla balance: every option the presets use goes back to default and challenge modlets are removed.",
      "Vanilla vyvážení: všechny volby, které presety používají, se vrátí na výchozí a challenge modlety se odeberou.",
      legacy={"GameDifficulty": "1", "EnemyDifficulty": "0"}),
    D("diff_scavenger", "🟢", 1, "easy", "difficulty", "Scavenger", "Scavenger",
      "Game difficulty 1/6 - you deal 200 % damage, take 50 %, zombies smell you only at walking pace.",
      "Obtížnost hry 1/6 - dáváš 200 % poškození, dostáváš 50 %, zombíci tě cítí jen krokem.",
      OFFICIAL("AAAKABKARDBNB"), {"GameDifficulty": "0"}),
    D("diff_adventurer", "🔵", 1, "easy", "difficulty", "Adventurer", "Adventurer",
      "Game difficulty 2/6 (game default) - you deal 150 % damage, take 75 %.",
      "Obtížnost hry 2/6 (výchozí ve hře) - dáváš 150 % poškození, dostáváš 75 %.",
      OFFICIAL("AAAJABJARFBNC"), {"GameDifficulty": "1"}),
    D("diff_nomad", "🟡", 2, "medium", "difficulty", "Nomad", "Nomad",
      "Game difficulty 3/6 - everything at 100 %.", "Obtížnost hry 3/6 - všechno na 100 %.",
      {}, {"GameDifficulty": "2"}),
    D("diff_warrior", "🟠", 3, "medium", "difficulty", "Warrior", "Warrior",
      "Game difficulty 4/6 - you deal 85 % damage and take 150 %.", "Obtížnost hry 4/6 - dáváš 85 % poškození a dostáváš 150 %.",
      OFFICIAL("AAAGABGARJ"), {"GameDifficulty": "3"}),
    D("diff_survivalist", "🔴", 4, "hard", "difficulty", "True Survivalist", "True Survivalist",
      "Game difficulty 5/6 - you deal 65 % damage, take 200 %, zombies smell you at sprint pace.",
      "Obtížnost hry 5/6 - dáváš 65 % poškození, dostáváš 200 %, zombíci tě cítí sprintem.",
      OFFICIAL("AAAEABEARKBNE"), {"GameDifficulty": "4"}),
    D("diff_insane", "☠️", 5, "extreme", "difficulty", "Insane", "Insane",
      "Game difficulty 6/6 - you deal 50 % damage, take 250 %, zombies track your smell at nightmare pace.",
      "Obtížnost hry 6/6 - dáváš 50 % poškození, dostáváš 250 %, zombíci tě stopují čichem rychlostí noční můry.",
      OFFICIAL("AAADABDARLBNF"), {"GameDifficulty": "5"}),
    # ------------------------------------------------------------------ zombies only
    D("z_easy", "🧟", 1, "easy", "zombies", "Zombies: Easy", "Zombíci: Lehcí",
      "Only zombies change: they hit softer (65 %), die faster (150 % damage taken), walk by day, jog at night, never rage and barely dent blocks.",
      "Mění se jen zombíci: bijí slaběji (65 %), umírají rychleji (dostávají 150 %), ve dne chodí, v noci klušou, nezuří a bloky skoro neničí.",
      {"EntityDamage": 0.65, "EntityIncomingDamage": 1.5, "ZombieMove": 0, "ZombieMoveNight": 1, "ZombieFeralMove": 2,
       "ZombieBMMove": 2, "ZombieFeralSense": 0, "AISmellMode": 1, "ZombieRageChance": 0, "BlockDamageAI": 0.75,
       "BlockDamageAIBM": 0.75, "BloodMoonEnemyCount": 6}),
    D("z_medium", "🧟", 3, "medium", "zombies", "Zombies: Medium", "Zombíci: Střední",
      "Tougher dead: they take only 85 % damage and hit for 125 %, jog by day, sprint at night, sense you at night and rage more often. Bases take more punishment.",
      "Odolnější mrtví: dostávají jen 85 % a bijí za 125 %, ve dne klušou, v noci sprintují, v noci tě vycítí a častěji zuří. Základny víc trpí.",
      {"EntityDamage": 1.25, "EntityIncomingDamage": 0.85, "ZombieMove": 1, "ZombieMoveNight": 3, "ZombieFeralMove": 3,
       "ZombieBMMove": 3, "ZombieFeralSense": 2, "AISmellMode": 3, "ZombieRageChance": 0.3, "BlockDamageAI": 1.25,
       "BlockDamageAIBM": 1.5, "BloodMoonEnemyCount": 10}),
    D("z_hard", "🧟", 4, "hard", "zombies", "Zombies: Hard", "Zombíci: Těžcí",
      "Bullet sponges: zombies take 65 % damage and hit for 150 %, run by day, nightmare speed at night, always feral, sprint after your smell, rage half the time and tear blocks apart. More of them at night.",
      "Houby na kulky: zombíci dostávají 65 % a bijí za 150 %, ve dne běží, v noci rychlostí noční můry, vždy ferální, čichem tě stíhají sprintem, zuří každou druhou ránu a trhají bloky. V noci jich je víc.",
      {"EntityDamage": 1.5, "EntityIncomingDamage": 0.65, "ZombieMove": 2, "ZombieMoveNight": 4, "ZombieFeralMove": 4,
       "ZombieBMMove": 4, "ZombieFeralSense": 3, "AISmellMode": 4, "ZombieRageChance": 0.5, "BlockDamageAI": 1.5,
       "BlockDamageAIBM": 2, "BloodMoonEnemyCount": 12, "BiomeNightEnemyDensity": 4, "BiomeNightZombieRespawn": 4}),
    D("z_extreme", "🧟", 5, "extreme", "zombies", "Zombies: Extreme", "Zombíci: Extrémní",
      "The real nightmare: zombies take only 35 % damage and hit for 200 %, sprint by day and night, always feral, track your smell at nightmare pace, rage on every hit, smash blocks at 250 %, spawn denser and respawn very fast. 24 per player on blood moons.",
      "Skutečná noční můra: zombíci dostávají jen 35 % a bijí za 200 %, sprintují ve dne i v noci, vždy ferální, čichem tě stopují rychlostí noční můry, zuří při každém zásahu, bloky ničí na 250 %, je jich víc a rychle se obnovují. 24 na hráče při krvavém měsíci.",
      {"EntityDamage": 2, "EntityIncomingDamage": 0.35, "ZombieMove": 3, "ZombieMoveNight": 4, "ZombieFeralMove": 4,
       "ZombieBMMove": 4, "ZombieFeralSense": 3, "AISmellMode": 5, "ZombieRageChance": 1, "BlockDamageAI": 2.5,
       "BlockDamageAIBM": 2.5, "BloodMoonEnemyCount": 24, "BiomeDayEnemyDensity": 4, "BiomeNightEnemyDensity": 5,
       "BiomeDayZombieRespawn": 4, "BiomeNightZombieRespawn": 5}),
    # ------------------------------------------------------------------ survival (hard to survive, not grindy)
    D("s_easy", "🥫", 1, "easy", "survival", "Survival: Easy", "Přežití: Lehké",
      "Comfortable survival: slow hunger and thirst, no temperature, low infection, gear barely wears, cheap traders who pay well. Keep your items on death.",
      "Pohodlné přežití: pomalý hlad a žízeň, bez teploty, nízká infekce, vybavení se skoro neopotřebuje, levní obchodníci, kteří dobře platí. Po smrti si necháš věci.",
      {"HungerMultiplier": 0.5, "ThirstMultiplier": 0.5, "TemperatureSurvival": False, "InfectionChance": 0.5,
       "ItemDegradation": 0.5, "StaminaUsage": 0.75, "DropOnDeath": 0, "DeathPenalty": 0, "TraderBuyPrices": 0.75,
       "TraderSellPrices": 1.5, "JarRefund": 0.8}),
    D("s_medium", "🥫", 3, "medium", "survival", "Survival: Medium", "Přežití: Střední",
      "Real pressure without the grind: faster hunger, thirst and infection, gear wears 1.5x, traders 1.5x more expensive. In return 1.25x XP and an extra skill point per level.",
      "Skutečný tlak bez grindu: rychlejší hlad, žízeň a infekce, vybavení se opotřebí 1,5×, obchodníci o 50 % dražší. Za to 1,25× XP a skill point navíc za level.",
      {"HungerMultiplier": 1.25, "ThirstMultiplier": 1.25, "InfectionChance": 1.25, "InfectionRate": 1.25,
       "ItemDegradation": 1.5, "TraderBuyPrices": 1.5, "TraderSellPrices": 0.75, "JarRefund": 0.4,
       "XPMultiplier": 1.25, "SkillPointsPerLevel": 2}),
    D("s_hard", "🥫", 4, "hard", "survival", "Survival: Hard", "Přežití: Těžké",
      "Every meal counts: 1.5x hunger and thirst, fast infection, heavy gear wear and repair loss, traders 2x the price paying half, less food and medicine, you drop your backpack on death. Progress stays quick: 1.5x XP, 2 skill points per level, more quests per day.",
      "Každé jídlo se počítá: 1,5× hlad a žízeň, rychlá infekce, velké opotřebení a ztráta při opravě, obchodníci 2× dražší a platí polovinu, méně jídla a léků, po smrti vypadne batoh. Postup zůstává rychlý: 1,5× XP, 2 skill pointy za level, víc questů denně.",
      {"HungerMultiplier": 1.5, "ThirstMultiplier": 1.5, "InfectionChance": 1.5, "InfectionRate": 1.5, "ItemDegradation": 2,
       "MaxDegradationAmount": 0.1, "TraderBuyPrices": 2, "TraderSellPrices": 0.5, "FoodLootCount": 0.65,
       "DrinkLootCount": 0.65, "MedicalLootCount": 0.65, "JarRefund": 0.2, "DropOnDeath": 3, "DeathPenalty": 2,
       "XPMultiplier": 1.5, "SkillPointsPerLevel": 2, "QuestProgressionDailyLimit": 6}),
    D("s_extreme", "🥫", 5, "extreme", "survival", "Survival: Extreme", "Přežití: Extrémní",
      "Scarcity: 2x hunger and thirst, triple infection, no jar refund, traders 3x the price paying a quarter, a third of the food and medicine, heavy encumbrance, injured after death and everything drops. Leveling is fast (2x XP, 3 points per level) so you fight the world, not the XP bar.",
      "Nedostatek: 2× hlad a žízeň, trojnásobná infekce, žádné vrácení sklenic, obchodníci 3× dražší a platí čtvrtinu, třetina jídla a léků, těžké zatížení, po smrti zranění a vypadne všechno. Levelování je rychlé (2× XP, 3 body za level), takže bojuješ se světem, ne s XP lištou.",
      {"HungerMultiplier": 2, "ThirstMultiplier": 2, "InfectionChance": 3, "InfectionRate": 2, "ItemDegradation": 2,
       "MaxDegradationAmount": 0.15, "TraderBuyPrices": 3, "TraderSellPrices": 0.25, "FoodLootCount": 0.35,
       "DrinkLootCount": 0.35, "MedicalLootCount": 0.35, "JarRefund": 0, "EncumbranceModifier": 0.7, "DropOnDeath": 1,
       "DeathPenalty": 2, "XPMultiplier": 2, "SkillPointsPerLevel": 3, "QuestProgressionDailyLimit": 8}),
    # ------------------------------------------------------------------ weapons & loot
    D("w_gun_nut", "🔫", 1, "easy", "weapons", "Gun Nut", "Střelec",
      "Twice as many guns and ammo, and better quality earlier (high loot stage). Skip the pipe-gun phase.",
      "Dvakrát víc zbraní a munice a lepší kvalita dřív (vysoký loot stage). Fáze trubkových zbraní odpadá.",
      {"RangedLootCount": 2, "AmmoLootCount": 2, "GlobalLSModifier": 1.5}),
    D("w_arsenal", "🎯", 3, "medium", "weapons", "Scavenged Arsenal", "Vybrakovaný arzenál",
      "Complete high-quality guns can turn up from day one (very high loot stage), but they are rare and can NOT be repaired. Ammo is a bit more common. Hard, but every find is a jackpot.",
      "Kompletní kvalitní zbraně můžeš najít už první den (velmi vysoký loot stage), ale jsou vzácné a NEJDOU opravit. Munice je o něco víc. Těžké, ale každý nález je výhra.",
      {"GlobalLSModifier": 2, "POITierLSModifier": 1.5, "RangedLootCount": 0.75, "AmmoLootCount": 1.25,
       "RepairTypes": 0, "ItemDegradation": 1.5}),
    D("w_disposable", "♻️", 3, "medium", "weapons", "Disposable Guns", "Zbraně na jedno použití",
      "Guns everywhere (3x) and good quality early, but they wear out very fast and cannot be repaired. Use it, lose it, loot the next one.",
      "Zbraně všude (3×) a brzy kvalitní, ale velmi rychle se opotřebí a nejdou opravit. Použij, zahoď, vylootuj další.",
      {"RangedLootCount": 3, "MeleeLootCount": 2, "AmmoLootCount": 1.5, "GlobalLSModifier": 1.5, "ItemDegradation": 2,
       "RepairTypes": 0}),
    D("w_ammo_famine", "🪓", 4, "hard", "weapons", "Ammo Famine", "Hladomor munice",
      "Guns are common, bullets are not (35 %). Melee weapons are everywhere and hit 25 % harder. Every shot is a decision.",
      "Zbraně jsou běžné, náboje ne (35 %). Zbraně na blízko jsou všude a bijí o 25 % víc. Každý výstřel je rozhodnutí.",
      {"AmmoLootCount": 0.35, "RangedLootCount": 1.25, "MeleeLootCount": 2, "MeleeDamage": 1.25, "ScrappingOutput": 0.75}),
    # ------------------------------------------------------------------ world threat (stronger zombies spawning)
    D("t_calm", "🌾", 1, "easy", "threat", "Quiet Countryside", "Klidný venkov",
      "Lower game stage everywhere and thinner hordes in biomes - weaker zombie types stay around longer.",
      "Nižší game stage všude a řidší hordy v biomech - slabší typy zombíků vydrží déle.",
      {"GlobalGSModifier": 0.5, "BiomeGSModifier": 0.5, "BiomeDayEnemyDensity": 2, "BiomeNightEnemyDensity": 3}),
    D("t_infested", "🏙️", 3, "medium", "threat", "Infested Cities", "Zamořená města",
      "Cities and biomes are packed: high enemy density and fast respawn day and night. Higher-tier POIs also give better loot.",
      "Města a biomy jsou nacpané: vysoká hustota nepřátel a rychlé obnovování ve dne i v noci. Vyšší POI dávají i lepší loot.",
      {"BiomeDayEnemyDensity": 4, "BiomeNightEnemyDensity": 5, "BiomeDayZombieRespawn": 4, "BiomeNightZombieRespawn": 4,
       "POITierLSModifier": 1.5}),
    D("t_wasteland", "☢️", 4, "hard", "threat", "Wasteland Everywhere", "Pustina všude",
      "Very high game stage: radiated and tougher zombie types show up in the forest and in towns long before they normally would. Loot stage rises too, so it pays off.",
      "Velmi vysoký game stage: ozáření a těžší typy zombíků se objevují v lese i ve městech dávno předtím, než by normálně měli. Roste i loot stage, takže se to vyplatí.",
      {"GlobalGSModifier": 2, "BiomeGSModifier": 1.5, "GlobalLSModifier": 1.5, "MaxEnemyTier": 5}),
    D("t_elite", "👑", 5, "extreme", "threat", "Elite Apocalypse", "Elitní apokalypsa",
      "Maximum game stage everywhere, elite zombies allowed in every biome, dense spawns and very fast respawn. Best loot stage as a reward.",
      "Maximální game stage všude, elitní zombíci v každém biomu, hustý spawn a velmi rychlé obnovování. Jako odměna nejlepší loot stage.",
      {"GlobalGSModifier": 2, "BiomeGSModifier": 2, "MaxEnemyTier": 5, "BiomeDayEnemyDensity": 4,
       "BiomeNightEnemyDensity": 5, "BiomeDayZombieRespawn": 5, "BiomeNightZombieRespawn": 5, "GlobalLSModifier": 2}),
    # ------------------------------------------------------------------ themed challenges
    D("weekend", "🏕️", 1, "easy", "themed", "Weekend Survivor", "Víkendový přeživší",
      "Relaxed co-op: you take half damage, learn 50 % faster, find more loot, and nights crawl instead of sprint. You keep your gear on death.",
      "Pohodový co-op: poloviční zranění, o 50 % rychlejší učení, víc lootu a noci se plouží místo sprintu. Po smrti si necháš věci.",
      {"IncomingDamage": 0.5, "XPMultiplier": 1.5, "GlobalLootCount": 1.5, "DayNightLength": 90, "ZombieMoveNight": 1,
       "BloodMoonFrequency": 10, "DropOnDeath": 0}, {"GameDifficulty": "0"}),
    D("loot_goblin", "💰", 1, "easy", "themed", "Loot Goblin", "Lootovací skřet",
      "Double loot everywhere, three times as many loot bags and more treasure maps. Containers refill every 5 days.",
      "Dvojnásobný loot všude, třikrát víc lootbagů a víc map k pokladům. Kontejnery se doplní každých 5 dní.",
      {"GlobalLootCount": 2, "LootBagChance": 3, "TreasureMapChance": 2, "DukesLootCount": 2, "LootRespawnDays": 5}),
    D("bookworm", "📚", 1, "easy", "themed", "Bookworm", "Knihomol",
      "Magazines and books everywhere, and every magazine teaches twice as much. Crafting unlocks fly by.",
      "Časopisy a knihy všude a každý časopis naučí dvakrát víc. Recepty se odemykají jedna radost.",
      {"CraftingMagazinesLootCount": 3, "BookLootCount": 2, "PointsPerMagazine": 2, "XPMultiplier": 1.25}),
    D("builders", "🧱", 1, "easy", "themed", "Builder's Paradise", "Ráj stavitelů",
      "Fast crafting, double harvesting and mining, bigger stacks, and zombies chew through blocks slower.",
      "Rychlé craftění, dvojnásobná těžba a sklizeň, větší stacky a zombíci pomaleji ničí bloky.",
      {"CraftingTime": 0.25, "HarvestingOutput": 2, "MiningOutput": 2, "StackSizeMultiplier": 2,
       "BlockDamageAI": 0.5, "BlockDamageAIBM": 0.75}),
    D("party", "🎉", 1, "easy", "themed", "Party Mode", "Párty mód",
      "Big heads, tiny zombies, moon gravity and celebrations on every kill. Pure chaos, great with friends.",
      "Velké hlavy, malí zombíci, měsíční gravitace a oslavy při každém zabití. Čistý chaos, nejlepší s kamarády.",
      {"SillyBigHeads": True, "SillyTinyZombies": True, "SillyLowGravity": 0.6, "SillyCelebrate": 1, "XPMultiplier": 1.5}),
    D("night_terrors", "🌒", 3, "medium", "themed", "Night Terrors", "Noční můry",
      "Calm, slow days. Nights are long and crowded, the dead sprint, track you by smell and are 15 % tougher.",
      "Klidné pomalé dny. Noci jsou dlouhé a plné, mrtví sprintují, stopují tě čichem a jsou o 15 % odolnější.",
      {"DayLightLength": 14, "ZombieMove": 0, "ZombieMoveNight": 4, "ZombieFeralSense": 2, "AISmellMode": 4,
       "ZombieFeralMove": 4, "EntityIncomingDamage": 0.85, "BiomeNightEnemyDensity": 4}, {"GameDifficulty": "3"}),
    D("horde_week", "🩸", 3, "medium", "themed", "Horde Week", "Týden hord",
      "Blood moon roughly every 3 days with doubled hordes that hit blocks harder. Build fast, build smart.",
      "Krvavý měsíc zhruba každé 3 dny s dvojnásobnými hordami, které víc ničí bloky. Stav rychle a chytře.",
      {"BloodMoonFrequency": 3, "BloodMoonRange": 1, "BloodMoonEnemyCount": 16, "ZombieBMMove": 4,
       "BlockDamageAIBM": 1.5}, {"GameDifficulty": "2"}),
    D("siege", "🏰", 3, "medium", "themed", "Siege Builders", "Obléhání",
      "Zombies tear through blocks, blood moons every 5 days. Engineering and base defense are everything.",
      "Zombíci trhají bloky, krvavý měsíc každých 5 dní. Inženýrství a obrana základny jsou všechno.",
      {"BlockDamageAI": 2, "BlockDamageAIBM": 2.5, "BloodMoonFrequency": 5, "BloodMoonEnemyCount": 12,
       "BlockDamage": 1.5}, {"GameDifficulty": "2"}),
    D("short_fuse", "⏱️", 3, "medium", "themed", "Short Fuse", "Krátká rozbuška",
      "Fast weekend run: 40-minute days, 1.5× XP and a blood moon every 4 days. Progress fast or die.",
      "Rychlý víkendový běh: 40minutové dny, 1,5× XP a krvavý měsíc každé 4 dny. Postupuj rychle, nebo zemři.",
      {"DayNightLength": 40, "XPMultiplier": 1.5, "BloodMoonFrequency": 4, "BloodMoonEnemyCount": 12},
      {"GameDifficulty": "2"}),
    D("black_market", "💸", 3, "medium", "themed", "Black Market", "Černý trh",
      "Traders charge four times the price, pay a quarter for your goods and have almost nothing in stock. Everything you need, you scavenge or craft.",
      "Obchodníci chtějí čtyřnásobek, za tvé věci dají čtvrtinu a nemají skoro nic na skladě. Co potřebuješ, musíš najít nebo vyrobit.",
      {"TraderBuyPrices": 4, "TraderSellPrices": 0.25, "TraderItemAbundance": 0.25, "VendingItemAbundance": 0.25},
      modlets=["trader_prices_legacy"]),
    D("lost_knowledge", "📕", 3, "medium", "themed", "Lost Knowledge", "Ztracené vědění",
      "Magazines and books are rare - recipes come slowly. In return you get two skill points per level. Choose your perks wisely.",
      "Časopisy a knihy jsou vzácné - recepty přichází pomalu. Za to dostaneš dva skill pointy za level. Vybírej perky s rozmyslem.",
      {"CraftingMagazinesLootCount": 0.25, "BookLootCount": 0.5, "SkillPointsPerLevel": 2}),
    D("feral_wasteland", "☣️", 4, "hard", "themed", "Feral Wasteland", "Divoká pustina",
      "Every zombie is feral, they run by day, track you by sound and smell, hit 50 % harder and take 25 % less damage. Storms are frequent.",
      "Všichni zombíci jsou ferální, přes den běhají, stopují tě podle zvuku a pachu, bijí o 50 % víc a vydrží o 25 % víc. Časté bouře.",
      {"ZombieFeralSense": 3, "ZombieMove": 2, "ZombieMoveNight": 3, "ZombieFeralMove": 4, "AISmellMode": 5,
       "StormFreq": 2, "EntityDamage": 1.5, "EntityIncomingDamage": 0.75}, {"GameDifficulty": "3", "EnemyDifficulty": "1"}),
    D("lootbag_only", "🎒", 4, "hard", "themed", "Lootbag Only", "Jen lootbagy",
      "The world is picked clean: containers are empty and trees, rocks and ore give nothing. Everything comes from zombie loot bags (much more common), quests, air drops and traders.",
      "Svět je vybrakovaný: kontejnery jsou prázdné a stromy, kameny ani ruda nic nedají. Všechno je z lootbagů zombíků (padají mnohem častěji), z questů, shozů a od obchodníků.",
      {"HarvestingOutput": 0, "MiningOutput": 0, "ScrappingOutput": 0.5, "TreasureMapChance": 2},
      {"GameDifficulty": "2"}, modlets=["empty_world_loot", "more_loot_bags"]),
    D("stone_age", "🪨", 4, "hard", "themed", "Stone Age", "Doba kamenná",
      "Quality caps at level 3 for crafting, loot and traders. No legendary gear - only skill, traps and good walls.",
      "Kvalita maximálně 3 pro craft, loot i obchodníky. Žádné legendární vybavení - jen um, pasti a dobré zdi.",
      {"CraftingMaxTier": 3, "LootMaxTier": 3, "TraderMaxTier": 3, "BloodMoonEnemyCount": 10}),
    D("hardcore", "💀", 4, "hard", "themed", "Hardcore Survivor", "Hardcore přeživší",
      "Permanent death: dying resets your character and drops everything. Every fight matters.",
      "Permanentní smrt: smrt resetuje postavu a vypadne všechno. Každý souboj se počítá.",
      {"DeathPenalty": 3, "DropOnDeath": 1, "DropOnQuit": 0, "ZombieMoveNight": 3, "IncomingDamage": 1.25},
      {"GameDifficulty": "3"}),
    D("apocalypse", "🔥", 5, "extreme", "themed", "Insane Apocalypse", "Šílená apokalypsa",
      "Everything at once: you deal half damage and take 250 %, zombies take half damage, feral sprinters day and night, triple hordes, heavy storms. Only for veterans.",
      "Všechno najednou: dáváš poloviční poškození a dostáváš 250 %, zombíci dostávají polovinu, ferální sprinteři ve dne i v noci, trojnásobné hordy, silné bouře. Jen pro veterány.",
      {"RangedDamage": 0.5, "MeleeDamage": 0.5, "IncomingDamage": 2.5, "EntityDamage": 1.5, "EntityIncomingDamage": 0.5,
       "ZombieMove": 3, "ZombieMoveNight": 4, "ZombieFeralMove": 4, "ZombieFeralSense": 3, "AISmellMode": 5,
       "ZombieRageChance": 0.5, "BloodMoonEnemyCount": 24, "StormFreq": 3, "DeathPenalty": 2},
      {"GameDifficulty": "5", "EnemyDifficulty": "1"}),
    # ------------------------------------------------------------------ official presets of The Fun Pimps (exact codes)
    D("o_almost_creative", "🛠️", 1, "easy", "official", "Almost Creative", "Almost Creative",
      "Official TFP preset: no enemies, no blood moons, very slow animals and 5x resources. Build in peace.",
      "Oficiální preset TFP: žádní nepřátelé, žádné krvavé měsíce, velmi málo zvířat a 5× suroviny. Stavění v klidu.",
      OFFICIAL("ABEABTBGBBBWADFN")),
    D("o_chibi", "🧸", 2, "easy", "official", "Chibi Mode", "Chibi Mode",
      "Official TFP preset: big heads, tiny zombies, low gravity, headshots only, faster everything and 1.5x XP.",
      "Oficiální preset TFP: velké hlavy, malí zombíci, nízká gravitace, jen headshoty, všechno rychlejší a 1,5× XP.",
      OFFICIAL("AAAJABJACJADJAEIARFAGIAHJAFJAIEAKEAJDASGENDBAAAYBAZBBBABDCAUBAMJBUEBSEBTEGCEGAEGBEAQBBIBBKEBLEBMBBNCCVHBZDCACCLDCMDCXBCYCDMJDAIDXIDNIDYIDOIDPGDTGEBGEEGAVCEXFCNDETFFLGFMJFOGFQCFRBFSBFUB")),
    D("o_dumpster", "🗑️", 3, "medium", "official", "Dumpster Diver", "Dumpster Diver",
      "Official TFP preset: 3x loot and daily air drops, but no mining, crops or seeds - you live off what you find.",
      "Oficiální preset TFP: 3× loot a shozy každý den, ale žádná těžba, plodiny ani semínka - žiješ z toho, co najdeš.",
      OFFICIAL("AAUABUCGCCCVLCABCXBDMKDALDFJDKDDXADNADYBDOAEABDVGDZFEXFFKA")),
    D("o_legacy", "📜", 3, "medium", "official", "Legacy Survival", "Legacy Survival",
      "Official TFP preset: classic-style survival - no crafting progression or quests, no biome hazards or encumbrance.",
      "Oficiální preset TFP: survival ve starém stylu - bez progrese craftění a questů, bez nebezpečí biomů a zatížení.",
      OFFICIAL("AAHIAJDBACAPAAUAAMLBREBUEBSCGCEGACBNCBPABOABVACDACVGCGACBACXBDDGDJIDNJDOJDSAELAEABEBGCNDFEDFIDFAFEOAFKAEPAEQA")),
    D("o_disaster", "🌪️", 3, "medium", "official", "Disaster Film", "Disaster Film",
      "Official TFP preset: 5x storms, gear wears very fast and degrades on death, but 2x loot.",
      "Oficiální preset TFP: 5× bouře, vybavení se rychle opotřebí a po smrti degraduje, ale 2× loot.",
      OFFICIAL("AAXBAYDAZFBDFBVACFHDAKDDJDKFAVFEKFFOJ")),
    D("o_caveman", "🦴", 4, "hard", "official", "Caveman Life", "Caveman Life",
      "Official TFP preset: tech level 0, half ranged damage, no map, compass, crops or vending.",
      "Oficiální preset TFP: tech úroveň 0, poloviční poškození na dálku, bez mapy, kompasu, plodin a automatů.",
      OFFICIAL("AAADABJBTFGBFCDACWBCAACQACRADNADOADWAEZAEWAFGAFKAFPA")),
    D("o_dying", "🥀", 4, "hard", "official", "Dying World", "Dying World",
      "Official TFP preset: loot never respawns, no loot bags, no repairs, no quests, traders nearly empty.",
      "Oficiální preset TFP: loot se neobnovuje, žádné lootbagy, žádné opravy, žádné questy, obchodníci skoro prázdní.",
      OFFICIAL("AAMABTBGBBCAACXADMADOAEBAEJAFEAFIAFDIFHIFJAEOAEPA")),
    D("o_matinee", "🎬", 4, "hard", "official", "Undead Matinee", "Undead Matinee",
      "Official TFP preset: slow but brutal classic-movie zombies (2x damage, always raging), scarce guns and ammo, melee rules.",
      "Oficiální preset TFP: pomalí, ale brutální zombíci jako ze starých filmů (2× poškození, vždy zuří), málo zbraní a munice, vládne boj na blízko.",
      OFFICIAL("AAAFABIACGADGAEIARJAGHAHEAFIAKEAJCBACAWBAXBAYDAZDBDGAPAAMFBUEBSEGCEGAEBFKBQEAQCBJABKABLBBMBBNCBPJCIDCJDCVEBZFCAGCFECYDDBDDCDDDDDEBDGDDHJDIBDKFAVEEKDFDFFHF")),
    D("o_later", "🏃", 4, "hard", "official", "Seven days Later", "Seven days Later",
      "Official TFP preset: runners everywhere day and night, dense fast-respawning hordes, you deal less and take more.",
      "Oficiální preset TFP: běžci všude ve dne i v noci, husté rychle se obnovující hordy, dáváš méně a dostáváš víc.",
      OFFICIAL("AAAGABGACGADGARJBACAWFAXBAYDAPABUEBSEGCEGAEBICBJCBKCBLCBMCBPFBZFBYC")),
    D("o_madmoles", "🐀", 5, "extreme", "official", "Madmoles Mayhem", "Madmoles Mayhem",
      "Official TFP preset: high game stage, nightmare ferals and smell tracking, scarce supplies, traders closed on blood moon.",
      "Oficiální preset TFP: vysoký game stage, ferální noční můry a stopování čichem, málo zásob, obchodníci zavřeno při krvavém měsíci.",
      OFFICIAL("AAAGABGACGBACAWBAXCAZEAPAAMIBUEBSEGCEGAEBFIBGIBHIBIBBKEBLEBNFCIDCJDCVDBZFDCDDDDDEDDFDDGDDJFEXF")),
    D("o_biteclub", "🩸", 5, "extreme", "official", "Bite Club", "Bite Club",
      "Official TFP preset: permadeath, no traders, loot never respawns, half the loot, sprint smell tracking.",
      "Oficiální preset TFP: permanentní smrt, žádní obchodníci, loot se neobnovuje, polovina lootu, stopování čichem sprintem.",
      OFFICIAL("AAAGABGACGADGARJAHJBADBDGBIBBMCBNEBPFBZFCFDCXADADEYA")),
]

GROUPS = ["difficulty", "zombies", "survival", "weapons", "threat", "themed", "official"]


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
    T("tough_dead", 2, "Tough dead (zombies take 65 % damage)", "Odolní mrtví (zombíci dostávají 65 %)", {"EntityIncomingDamage": 0.65}),
    T("fragile_dead", -2, "Fragile dead (zombies take 150 % damage)", "Křehcí mrtví (zombíci dostávají 150 %)", {"EntityIncomingDamage": 1.5}),
    T("rage", 1, "Rage (zombies rage on half the hits)", "Vztek (zombíci zuří při každém druhém zásahu)", {"ZombieRageChance": 0.5}, flavor=True),
    T("infested", 2, "Infested (dense, fast-respawning spawns)", "Zamoření (hustý spawn, rychlé obnovování)",
      {"BiomeDayEnemyDensity": 4, "BiomeNightEnemyDensity": 5, "BiomeNightZombieRespawn": 4}),
    T("high_stage", 2, "High game stage (tougher types early, better loot)", "Vysoký game stage (dřív těžší typy, lepší loot)",
      {"GlobalGSModifier": 1.5, "GlobalLSModifier": 1.5}, flavor=True),
    T("no_repair", 1, "No repairs (find replacements)", "Bez oprav (hledej náhrady)", {"RepairTypes": 0}, flavor=True),
    T("armory", -1, "Armory (2x guns and ammo)", "Zbrojnice (2× zbraně a munice)", {"RangedLootCount": 2, "AmmoLootCount": 2}),
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
            "tiers": list(TIERS), "groups": GROUPS}
