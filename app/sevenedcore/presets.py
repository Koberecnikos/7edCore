"""Difficulty presets and challenges. Loot stays at standard values on purpose - the
challenge comes from danger, pacing and pressure, not from starving the players.
Only properties that exist in the server's serverconfig.xml are applied."""

STANDARD = {
    "GameDifficulty": "1", "XPMultiplier": "100", "BlockDamagePlayer": "100", "BlockDamageAI": "100",
    "BlockDamageAIBM": "100", "DayNightLength": "60", "DayLightLength": "18", "DeathPenalty": "1",
    "DropOnDeath": "1", "DropOnQuit": "0", "EnemySpawnMode": "true", "EnemyDifficulty": "0",
    "ZombieFeralSense": "0", "ZombieMove": "0", "ZombieMoveNight": "3", "ZombieFeralMove": "3",
    "ZombieBMMove": "3", "AISmellMode": "3", "BloodMoonFrequency": "7", "BloodMoonRange": "0",
    "BloodMoonWarning": "8", "BloodMoonEnemyCount": "8", "LootAbundance": "100", "LootRespawnDays": "7",
    "AirDropFrequency": "72", "MaxSpawnedZombies": "64", "StormFreq": "100", "PartySharedKillRange": "100",
}


def _p(base=None, **kw):
    d = dict(base or STANDARD)
    d.update({k: str(v) for k, v in kw.items()})
    return d


PRESETS = [
    {"id": "standard", "icon": "⚖️", "level": 1,
     "name": {"en": "Standard", "cs": "Standard"},
     "desc": {"en": "Vanilla balance. Good starting point for a new group.",
              "cs": "Vanilla vyvážení. Dobrý start pro novou partu."},
     "values": _p()},
    {"id": "night_terrors", "icon": "🌒", "level": 3,
     "name": {"en": "Night Terrors", "cs": "Noční můry"},
     "desc": {"en": "Calm, slow days - nights are long and the dead sprint and smell you. Plan every evening.",
              "cs": "Klidné pomalé dny – noci jsou dlouhé, mrtví sprintují a cítí tě. Každý večer je potřeba naplánovat."},
     "values": _p(GameDifficulty=3, DayLightLength=14, ZombieMove=0, ZombieMoveNight=4, ZombieFeralSense=2,
                  AISmellMode=4, ZombieFeralMove=4)},
    {"id": "horde_week", "icon": "🩸", "level": 3,
     "name": {"en": "Horde Week", "cs": "Týden hord"},
     "desc": {"en": "Blood moon every ~3 days (random ±1) with doubled hordes that hit harder. Build fast, build smart.",
              "cs": "Krvavý měsíc zhruba každé 3 dny (±1) s dvojnásobnými hordami, které víc ničí. Stav rychle a chytře."},
     "values": _p(GameDifficulty=2, BloodMoonFrequency=3, BloodMoonRange=1, BloodMoonEnemyCount=16,
                  ZombieBMMove=4, BlockDamageAIBM=150)},
    {"id": "feral_wasteland", "icon": "☣️", "level": 4,
     "name": {"en": "Feral Wasteland", "cs": "Divoká pustina"},
     "desc": {"en": "Every zombie is feral, they run by day and track you by sound and smell. Storms are frequent.",
              "cs": "Všichni zombíci jsou ferální, přes den běhají a stopují tě podle zvuku a pachu. Časté bouře."},
     "values": _p(GameDifficulty=3, EnemyDifficulty=1, ZombieFeralSense=3, ZombieMove=2, ZombieMoveNight=3,
                  ZombieFeralMove=4, AISmellMode=5, StormFreq=200)},
    {"id": "siege", "icon": "🏰", "level": 3,
     "name": {"en": "Siege Builders", "cs": "Obléhání"},
     "desc": {"en": "Zombies tear through blocks, blood moons every 5 days. Engineering and base defense are everything.",
              "cs": "Zombíci trhají bloky, krvavý měsíc každých 5 dní. Inženýrství a obrana základny jsou všechno."},
     "values": _p(GameDifficulty=2, BlockDamageAI=200, BlockDamageAIBM=250, BloodMoonFrequency=5,
                  BloodMoonEnemyCount=12, BlockDamagePlayer=150)},
    {"id": "short_fuse", "icon": "⏱️", "level": 3,
     "name": {"en": "Short Fuse", "cs": "Krátká rozbuška"},
     "desc": {"en": "Fast weekend run: 40-minute days, 1.5× XP and a blood moon every 4 days. Progress fast or die.",
              "cs": "Rychlý víkendový běh: 40minutové dny, 1,5× XP a krvavý měsíc každé 4 dny. Postupuj rychle, nebo zemři."},
     "values": _p(GameDifficulty=2, DayNightLength=40, XPMultiplier=150, BloodMoonFrequency=4, BloodMoonEnemyCount=12)},
    {"id": "hardcore", "icon": "💀", "level": 4,
     "name": {"en": "Hardcore Survivor", "cs": "Hardcore přeživší"},
     "desc": {"en": "Permanent death: dying resets your character and drops everything. Every fight matters.",
              "cs": "Permanentní smrt: smrt resetuje postavu a vypadne všechno. Každý souboj se počítá."},
     "values": _p(GameDifficulty=3, DeathPenalty=3, DropOnDeath=1, DropOnQuit=0, ZombieMoveNight=3)},
    {"id": "insane", "icon": "🔥", "level": 5,
     "name": {"en": "Insane Apocalypse", "cs": "Šílená apokalypsa"},
     "desc": {"en": "Everything at once: Insane difficulty, feral sprinters day and night, triple hordes. Only for veterans.",
              "cs": "Všechno najednou: obtížnost Insane, ferální sprinteři ve dne i v noci, trojnásobné hordy. Jen pro veterány."},
     "values": _p(GameDifficulty=5, EnemyDifficulty=1, ZombieMove=3, ZombieMoveNight=4, ZombieFeralMove=4,
                  ZombieFeralSense=3, AISmellMode=5, BloodMoonEnemyCount=24, StormFreq=300, DeathPenalty=2)},
]
