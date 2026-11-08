"""Metadata for serverconfig.xml properties: category, settings level, input type, labels (en/cs).

Levels: basic (the few things everyone changes), detailed (gameplay, by category),
advanced (networking, permissions, admin interfaces). Properties found in a server's
config but missing here are shown under "Other" in the detailed level, so new game
versions keep working without a panel update."""

B, N, S, T, P = "bool", "number", "select", "text", "password"

CATEGORIES = [
    # id, level, en, cs
    ("server", "basic", "Server", "Server"),
    ("world", "basic", "World", "Svět"),
    ("challenge", "basic", "Difficulty & players", "Obtížnost a hráči"),
    ("gameplay", "detailed", "Gameplay", "Hratelnost"),
    ("death", "detailed", "Death & respawn", "Smrt a respawn"),
    ("zombies", "detailed", "Zombies & animals", "Zombíci a zvířata"),
    ("bloodmoon", "detailed", "Blood moon", "Krvavý měsíc"),
    ("blocks", "detailed", "Block damage", "Poškození bloků"),
    ("loot", "detailed", "Loot & air drops", "Loot a shozy"),
    ("multiplayer", "detailed", "Multiplayer & PvP", "Multiplayer a PvP"),
    ("landclaim", "detailed", "Land claims", "Land claimy"),
    ("performance", "detailed", "Performance", "Výkon"),
    ("other", "detailed", "Other", "Ostatní"),
    ("network", "advanced", "Network & listing", "Síť a výpis serveru"),
    ("permissions", "advanced", "Permissions & slots", "Oprávnění a sloty"),
    ("admin", "advanced", "Admin interfaces", "Administrátorská rozhraní"),
]

ZSPEED = [["0", "Walk", "Chůze"], ["1", "Jog", "Klus"], ["2", "Run", "Běh"], ["3", "Sprint", "Sprint"],
          ["4", "Nightmare", "Noční můra"]]
DIFF = [["0", "Scavenger", "Scavenger"], ["1", "Adventurer", "Adventurer"], ["2", "Nomad", "Nomad"],
        ["3", "Warrior", "Warrior"], ["4", "Survivalist", "Survivalist"], ["5", "Insane", "Insane"]]
PERM = "0 = admin … 1000 = everyone / 0 = admin … 1000 = všichni"

# name: (category, type, extra, en label, cs label, en help, cs help)
P_ = {}


def _add(cat, name, typ, en, cs, hen="", hcs="", **extra):
    P_[name] = {"cat": cat, "type": typ, "label": {"en": en, "cs": cs}, "help": {"en": hen, "cs": hcs}, **extra}


# ---- basic
_add("server", "ServerName", T, "Server name", "Název serveru", "Shown in the server browser.", "Zobrazí se v seznamu serverů.")
_add("server", "ServerDescription", T, "Description", "Popis")
_add("server", "ServerPassword", P, "Join password", "Heslo pro připojení", "Empty = anyone can join.", "Prázdné = může se připojit kdokoli.")
_add("world", "GameWorld", T, "World", "Svět", "Navezgane, a Pregen world, RWG (generate) or a generated world name - pick it in the World tab.",
     "Navezgane, Pregen svět, RWG (vygenerovat) nebo název vygenerovaného světa - vyber v záložce Svět.", managed="world")
_add("world", "WorldGenSeed", T, "World seed (RWG)", "Seed světa (RWG)", "Used when the world is RWG.", "Použije se, když je svět RWG.")
_add("world", "WorldGenSize", S, "World size (RWG)", "Velikost světa (RWG)", "Bigger worlds take longer to generate and need more RAM.",
     "Větší svět se déle generuje a potřebuje víc RAM.",
     options=[[v, v, v] for v in ("4096", "6144", "8192", "10240")])
_add("world", "GameName", T, "Save name", "Název uložené hry", "Each name is a separate save of the world.", "Každý název je samostatná uložená hra.")
_add("challenge", "GameDifficulty", S, "Difficulty", "Obtížnost", options=DIFF)
_add("challenge", "ServerMaxPlayerCount", N, "Max players", "Max hráčů", min=1, max=64)
_add("challenge", "PartySharedKillRange", N, "Party shared XP range (m)", "Dosah sdílení XP v partě (m)",
     "Party members within this distance share kill XP.", "Členové party v této vzdálenosti sdílí XP za zabití.", min=0, max=10000)
_add("challenge", "XPMultiplier", N, "XP multiplier (%)", "Násobič XP (%)", min=0, max=300)
_add("challenge", "GameMode", S, "Game mode", "Herní mód", options=[["GameModeSurvival", "Survival", "Survival"]])

# ---- detailed
_add("gameplay", "DayNightLength", N, "Real minutes per in-game day", "Reálné minuty na herní den", min=10, max=240)
_add("gameplay", "DayLightLength", N, "Daylight hours", "Hodin denního světla", min=0, max=24)
_add("gameplay", "BiomeProgression", B, "Biome hazards", "Nebezpečí biomů", "Harsh biomes hurt until you have the right gear (V2+).",
     "Drsné biomy zraňují, dokud nemáš vybavení (V2+).")
_add("gameplay", "StormFreq", N, "Storm frequency (%)", "Četnost bouří (%)", min=0, max=500)
_add("gameplay", "BuildCreate", B, "Creative / cheat mode", "Kreativní / cheat mód")
_add("gameplay", "QuestProgressionDailyLimit", N, "Quests per day toward tier progress", "Úkolů denně pro postup tieru", min=0, max=20)
_add("gameplay", "JarRefund", N, "Jar refund (%)", "Vrácení sklenic (%)", min=0, max=100)
_add("death", "DeathPenalty", S, "Death penalty", "Trest za smrt",
     options=[["0", "None", "Žádný"], ["1", "XP penalty", "Ztráta XP"], ["2", "Injured", "Zranění"], ["3", "Permanent death", "Permanentní smrt"]])
_add("death", "DropOnDeath", S, "Drop on death", "Po smrti vypadne",
     options=[["0", "Nothing", "Nic"], ["1", "Everything", "Všechno"], ["2", "Toolbelt only", "Jen opasek"],
              ["3", "Backpack only", "Jen batoh"], ["4", "Delete all", "Vše se smaže"]])
_add("death", "DropOnQuit", S, "Drop on quit", "Při odpojení vypadne",
     options=[["0", "Nothing", "Nic"], ["1", "Everything", "Všechno"], ["2", "Toolbelt only", "Jen opasek"], ["3", "Backpack only", "Jen batoh"]])
_add("death", "BedrollDeadZoneSize", N, "Bedroll no-spawn radius", "Okruh bez spawnu u spacáku", min=0, max=100)
_add("death", "BedrollExpiryTime", N, "Bedroll expiry (real days offline)", "Expirace spacáku (dny offline)", min=0, max=365)
_add("death", "PlayerSafeZoneLevel", N, "Safe zone until level", "Bezpečná zóna do levelu", min=0, max=300)
_add("death", "PlayerSafeZoneHours", N, "Safe zone hours", "Hodin bezpečné zóny", min=0, max=48)
_add("death", "AllowSpawnNearFriend", S, "Spawn near friend", "Spawn u přítele",
     options=[["0", "Disabled", "Vypnuto"], ["1", "Always", "Vždy"], ["2", "Only in forest biome", "Jen v lesním biomu"]])
_add("zombies", "EnemySpawnMode", B, "Enemies spawn", "Nepřátelé se spawnují")
_add("zombies", "EnemyDifficulty", S, "Enemy type", "Typ nepřátel", options=[["0", "Normal", "Normální"], ["1", "Feral", "Ferální"]])
_add("zombies", "ZombieFeralSense", S, "Feral sense", "Ferální smysly",
     options=[["0", "Off", "Vypnuto"], ["1", "Day", "Ve dne"], ["2", "Night", "V noci"], ["3", "All the time", "Pořád"]])
_add("zombies", "ZombieMove", S, "Speed by day", "Rychlost ve dne", options=ZSPEED)
_add("zombies", "ZombieMoveNight", S, "Speed at night", "Rychlost v noci", options=ZSPEED)
_add("zombies", "ZombieFeralMove", S, "Feral speed", "Rychlost ferálních", options=ZSPEED)
_add("zombies", "ZombieBMMove", S, "Blood moon speed", "Rychlost při krvavém měsíci", options=ZSPEED)
_add("zombies", "AISmellMode", S, "Smell tracking", "Stopování čichem", options=[["0", "Off", "Vypnuto"]] + ZSPEED[:4] + [["5", "Nightmare", "Noční můra"]])
_add("zombies", "MaxSpawnedZombies", N, "Max zombies on map", "Max zombíků na mapě", "Higher = more CPU and RAM.", "Víc = víc CPU a RAM.", min=1, max=200)
_add("zombies", "MaxSpawnedAnimals", N, "Max animals on map", "Max zvířat na mapě", min=0, max=200)
_add("bloodmoon", "BloodMoonFrequency", N, "Every N days", "Každých N dní", "0 = never.", "0 = nikdy.", min=0, max=100)
_add("bloodmoon", "BloodMoonRange", N, "Random ± days", "Náhodně ± dní", min=0, max=50)
_add("bloodmoon", "BloodMoonWarning", N, "Warning hour (-1 off)", "Hodina varování (-1 vyp.)", min=-1, max=23)
_add("bloodmoon", "BloodMoonEnemyCount", N, "Zombies per player", "Zombíků na hráče", min=0, max=64)
_add("blocks", "BlockDamagePlayer", N, "Player block damage (%)", "Poškození bloků hráčem (%)", min=0, max=500)
_add("blocks", "BlockDamageAI", N, "Zombie block damage (%)", "Poškození bloků zombíky (%)", min=0, max=500)
_add("blocks", "BlockDamageAIBM", N, "Blood moon block damage (%)", "Poškození bloků při krvavém měsíci (%)", min=0, max=500)
_add("loot", "LootAbundance", N, "Loot abundance (%)", "Množství lootu (%)", min=0, max=300)
_add("loot", "LootRespawnDays", N, "Loot respawn (days)", "Obnova lootu (dny)", min=-1, max=100)
_add("loot", "AirDropFrequency", N, "Air drop every N game hours", "Shoz každých N herních hodin", "0 = never.", "0 = nikdy.", min=0, max=1000)
_add("loot", "AirDropMarker", B, "Mark air drops on map", "Označit shozy na mapě")
_add("multiplayer", "PlayerKillingMode", S, "Player killing", "Zabíjení hráčů",
     options=[["0", "No killing", "Zakázáno"], ["1", "Allies only", "Jen spojenci"], ["2", "Strangers only", "Jen cizí"], ["3", "Everyone", "Všichni"]])
_add("landclaim", "LandClaimCount", N, "Claims per player", "Claimů na hráče", min=0, max=50)
_add("landclaim", "LandClaimSize", N, "Claim size (blocks)", "Velikost claimu (bloky)", min=1, max=201)
_add("landclaim", "LandClaimDeadZone", N, "Min distance between claims", "Min. vzdálenost claimů", min=0, max=200)
_add("landclaim", "LandClaimExpiryTime", N, "Expiry (real days offline)", "Expirace (dny offline)", min=0, max=365)
_add("landclaim", "LandClaimDecayMode", S, "Decay mode", "Způsob útlumu",
     options=[["0", "Slow (linear)", "Pomalý"], ["1", "Fast (exponential)", "Rychlý"], ["2", "None until expired", "Žádný do expirace"]])
_add("landclaim", "LandClaimOnlineDurabilityModifier", N, "Hardness while online (0 = invulnerable)", "Odolnost online (0 = nezničitelné)", min=0, max=100)
_add("landclaim", "LandClaimOfflineDurabilityModifier", N, "Hardness while offline (0 = invulnerable)", "Odolnost offline (0 = nezničitelné)", min=0, max=100)
_add("landclaim", "LandClaimOfflineDelay", N, "Offline delay (minutes)", "Zpoždění offline (min)", min=0, max=1440)
_add("performance", "ServerMaxAllowedViewDistance", N, "Max view distance", "Max dohled", "Lower = less CPU/RAM.", "Nižší = méně CPU/RAM.", min=6, max=12)
_add("performance", "MaxQueuedMeshLayers", N, "Max queued mesh layers", "Max fronta mesh vrstev", min=0, max=10000)
_add("performance", "MaxChunkAge", N, "Reset untouched chunks after (days, -1 never)", "Reset nenavštívených chunků (dny, -1 nikdy)", min=-1, max=1000)
_add("performance", "SaveDataLimit", N, "Save size limit (MB, -1 none)", "Limit velikosti uložení (MB, -1 bez)", min=-1, max=1000000)
_add("performance", "DynamicMeshEnabled", B, "Dynamic mesh (distant buildings)", "Dynamický mesh (vzdálené stavby)")
_add("performance", "DynamicMeshLandClaimOnly", B, "Dynamic mesh only in land claims", "Dynamický mesh jen v claimech")
_add("performance", "DynamicMeshLandClaimBuffer", N, "Dynamic mesh claim buffer", "Okraj dynamického meshe", min=0, max=10)
_add("performance", "DynamicMeshMaxItemCache", N, "Dynamic mesh item cache", "Cache dynamického meshe", min=1, max=10)
_add("performance", "MaxUncoveredMapChunksPerPlayer", N, "Max uncovered map chunks / player", "Max odkrytých chunků mapy / hráč", min=0, max=10000000)
_add("performance", "ServerMaxWorldTransferSpeedKiBs", N, "World transfer speed (KiB/s)", "Rychlost přenosu světa (KiB/s)", min=64, max=1300)
_add("other", "TwitchBloodMoonAllowed", B, "Twitch actions during blood moon", "Twitch akce při krvavém měsíci")

# ---- advanced
_add("network", "ServerPort", N, "Game port", "Herní port",
     "Assigned by 7edCore per server. Changing it also requires publishing the port in Docker.",
     "Přiděluje 7edCore. Změna vyžaduje i publikovat port v Dockeru.", min=1024, max=65535, managed="port")
_add("network", "ServerVisibility", S, "Visibility", "Viditelnost",
     options=[["2", "Public", "Veřejný"], ["1", "Friends only", "Jen přátelé"], ["0", "Not listed", "Nezveřejněný"]])
_add("network", "ServerDisabledNetworkProtocols", T, "Disabled network protocols", "Vypnuté síťové protokoly",
     "Comma separated: SteamNetworking, LiteNetLib.", "Čárkou oddělené: SteamNetworking, LiteNetLib.")
_add("network", "Region", S, "Region", "Region", options=[[v, v, v] for v in (
    "NorthAmericaEast", "NorthAmericaWest", "CentralAmerica", "SouthAmerica", "Europe", "Russia", "Asia",
    "MiddleEast", "Africa", "Oceania")])
_add("network", "Language", T, "Server language", "Jazyk serveru")
_add("network", "ServerWebsiteURL", T, "Website URL", "URL webu")
_add("network", "ServerLoginConfirmationText", T, "Join confirmation text", "Text potvrzení při připojení")
_add("network", "ServerAllowCrossplay", B, "Allow crossplay (console players)", "Povolit crossplay (konzole)",
     "Crossplay requires EAC on and max 8 players.", "Crossplay vyžaduje zapnuté EAC a max 8 hráčů.")
_add("network", "EACEnabled", B, "Easy Anti-Cheat", "Easy Anti-Cheat", "Turn off for most DLL mods.", "Pro většinu DLL módů vypni.")
_add("network", "IgnoreEOSSanctions", B, "Ignore EOS sanctions", "Ignorovat EOS sankce")
_add("permissions", "ServerAdminSlots", N, "Admin slots", "Admin sloty", min=0, max=64)
_add("permissions", "ServerAdminSlotsPermission", N, "Admin slot permission level", "Úroveň pro admin sloty", PERM, PERM, min=0, max=1000)
_add("permissions", "ServerReservedSlots", N, "Reserved slots", "Rezervované sloty", min=0, max=64)
_add("permissions", "ServerReservedSlotsPermission", N, "Reserved slot permission level", "Úroveň pro rezervované sloty", PERM, PERM, min=0, max=1000)
_add("permissions", "AdminFileName", T, "Admin file name", "Název admin souboru",
     "Inside the server's save folder. Edit it in Files.", "Ve složce uložení serveru. Uprav v Souborech.")
_add("permissions", "PersistentPlayerProfiles", B, "Lock player profiles", "Zamknout profily hráčů",
     "Players always join with their last used character.", "Hráči se připojí vždy s naposledy použitou postavou.")
_add("permissions", "HideCommandExecutionLog", S, "Hide command log", "Skrýt log příkazů",
     options=[["0", "Show everything", "Zobrazit vše"], ["1", "Hide only from Telnet/panel", "Skrýt jen z Telnetu/panelu"],
              ["2", "Also hide from remote clients", "Skrýt i vzdáleným klientům"], ["3", "Hide everything", "Skrýt vše"]])
_add("permissions", "TwitchServerPermission", N, "Twitch integration permission level", "Úroveň pro Twitch integraci", PERM, PERM, min=0, max=1000)
_add("admin", "WebDashboardEnabled", B, "Web dashboard & map", "Webový dashboard a mapa",
     "The game's own web map. Port is assigned by 7edCore.", "Herní webová mapa. Port přiděluje 7edCore.")
_add("admin", "WebDashboardPort", N, "Web dashboard port", "Port webového dashboardu", managed="port", min=1024, max=65535)
_add("admin", "WebDashboardUrl", T, "Web dashboard public URL", "Veřejná URL dashboardu")
_add("admin", "EnableMapRendering", B, "Render the map for the dashboard", "Vykreslovat mapu pro dashboard")
_add("admin", "TelnetEnabled", B, "Telnet", "Telnet", "Always on - 7edCore uses it for the console.", "Vždy zapnuto - 7edCore ho používá pro konzoli.", managed="locked")
_add("admin", "TelnetPort", N, "Telnet port", "Telnet port", "Internal, assigned by 7edCore.", "Interní, přiděluje 7edCore.", managed="port")
_add("admin", "TelnetPassword", P, "Telnet password", "Heslo Telnetu")
_add("admin", "TelnetFailedLoginLimit", N, "Telnet failed login limit", "Limit chybných přihlášení Telnetu", min=0, max=100)
_add("admin", "TelnetFailedLoginsBlocktime", N, "Telnet block time (s)", "Doba blokace Telnetu (s)", min=0, max=86400)
_add("admin", "TerminalWindowEnabled", B, "Terminal window (Windows only)", "Okno terminálu (jen Windows)")
_add("admin", "UserDataFolder", T, "User data folder", "Složka uživatelských dat", "Managed by 7edCore.", "Spravuje 7edCore.", managed="locked")

PROPS = P_


def catalog():
    return {"categories": [{"id": c, "level": lv, "label": {"en": en, "cs": cs}} for c, lv, en, cs in CATEGORIES],
            "props": PROPS}
