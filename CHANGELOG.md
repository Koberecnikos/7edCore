# Changelog

## 1.7.0 - 2026-11-17

- Mods: problems from the last start, per mod - code that did not start (with the mod's reason), built for another game version (missing game types, Harmony patch targets that no longer exist), XML changes that did not apply, missing dependencies (e.g. a weapon pack without its resources mod), and game XML files that failed to load because of a mod (with the follow-up failures of recipes / loot / traders). Red / yellow tags in the list, a summary above it and a notice in the Overview
- Console → 🩺 Analyse the log: all errors grouped by mod, other errors, and the messages that are normal on a dedicated server (shaders, textures, world generator …) counted separately
- Mods → Check compatibility with an installed game version, without starting the server: types, methods and fields a code mod uses from the game's Assembly-CSharp.dll, Harmony patch targets, and every XPath patch against the game's own XML (patches that only touch another mod's content are recognised)
- Docker image: adds lxml and dnfile for the checks

## 1.6.1 - 2026-11-17

- Fix: the panel no longer runs the game's `mem` command every 30 s. Besides printing FPS it unloads assets and runs the garbage collector, which froze modded servers for ~0.8 s each time. FPS / chunks / zombies are now measured automatically only while nobody is online, or on request ("Measure now" in the FPS tile)
- New and duplicated servers get telnet and web map ports no other server uses, even if ports were changed by hand

## 1.6.0 - 2026-11-17

- Mods: upload several ZIPs at once (file picker or drag and drop) with progress and a Cancel button. A batch is installed only after every file arrived complete and passed the check, so a cancelled or broken upload never leaves a half-installed mod; leftover temp files are cleaned at startup
- Mods: search, sort (name, size, install date, status) and totals (number of mods, enabled, total size)
- Mods → ⚙ Configure: lists the mod's own settings files and edits them in the panel, with XML/JSON validation, "Reset to original" and a restart hint; edits are kept on mod updates
- Duplicate server as a 1:1 replica: game + panel settings, all mods with their configs and metadata, admins/whitelist/bans and optionally worlds and saves (copied in the background, the source is saved first if it runs)
- New / duplicated server: choose the game port; the first free one (26900, 26910, …) is preselected
- Dynamic day length: day length follows the number of players online (reference count, % per player below / above, shortest / longest day); time can stand still while nobody is online; preview and measured speed in the panel
- Web map: settings dialog with diagnostics (enabled, port, access, does the dashboard answer), "viewable without login" writes the `web.map` permission into serveradmin.xml (the missing permission was why the map asked for a Steam login), and "Render the whole map"
- README: screenshots of every main page

## 1.5.1 - 2026-11-09

- Overview → Quick actions: checkbox "Start automatically when the machine starts" per server

## 1.5.0 - 2026-11-08

- Game difficulty presets exactly as in the PC game (Scavenger … Insane), taken from the game's own Sandbox presets
- New preset groups: Zombies (Easy / Medium / Hard / Extreme - health, damage, speed, senses, rage, block damage, density), Survival (Easy … Extreme - harder survival with generous XP), Weapons & loot (Gun Nut, Scavenged Arsenal with unrepairable rare guns, Disposable Guns, Ammo Famine), World threat (stronger zombie types outside their biomes, infested cities, elite apocalypse)
- All 11 official presets of The Fun Pimps (Almost Creative, Chibi Mode, Dumpster Diver, Legacy Survival, Disaster Film, Caveman Life, Dying World, Undead Matinee, Seven days Later, Madmoles Mayhem, Bite Club)
- Insane Apocalypse, Feral Wasteland and Night Terrors now also make zombies tougher; 7 new random twists
- Web map: link and one-click "Enable web map" in Overview / Quick actions (uses the server's own web port)
- Activity feedback everywhere: spinner on the clicked button, progress bar for every request, upload percentage for ZIP uploads

## 1.4.0 - 2026-11-08

- Panel → 7edCore updates: choose "Latest (automatic)" or pin any release from GitHub (with release notes); switching applies within a minute
- The host updater pins the image through `SEVENEDCORE_TAG` in `.env` and keeps itself up to date

## 1.3.0 - 2026-11-08

- User accounts instead of one shared password: admin, operator and viewer roles, per-user server access
- First visit creates the admin account (user name + password); an existing panel password becomes the account "admin"
- Panel → Users: add users, change roles and servers, set passwords, delete; everyone can change their own password
- Lost password: `7edcore user reset NAME` on the host prints a new one; also `7edcore user list | add | role | delete`

## 1.2.0 - 2026-11-08

- Combine presets: add several presets (and random rolls) to a combination, drag to order them; the preset on top has priority and overrides the same settings of the ones below
- Preview shows which preset each change comes from and which settings were overridden
- The applied combination is remembered per server
- Value labels like "{0} Days" now show the real numbers

## 1.1.0 - 2026-11-08

- Full support for V3 Sandbox Options: all 165 options editable in Game settings (Basic / Detailed), SandboxCode read, written and pasteable in Advanced
- Presets now work on V3 (SandboxCode) and on older versions (serverconfig.xml) alike, with a preview of every change before applying; applying a preset undoes the previous one
- New presets: Weekend Survivor, Loot Goblin, Bookworm, Builder's Paradise, Party Mode, Black Market, Lost Knowledge, Lootbag Only, Stone Age
- Random challenge (Easy / Medium / Hard): 3-5 balanced twists from a pool of 32, reroll until you like it, reproducible by seed
- Challenge modlets: server-side XML patches generated per server (e.g. empty world loot for Lootbag Only), no client install
- tools/sandbox_extract.py to regenerate the option tables for new game versions

## 1.0.0 - 2026-11-08

First public release.

- Multiple 7 Days to Die servers per machine, each with its own ports, saves, mods, backups and schedule
- Game version (Steam branch) per server with save compatibility warnings
- Game / mod update policies with pre-update backups; major game updates never automatic
- Mod install from ZIP / GitHub / URL, compatible-release lookup, update with carry-over of edited files
- Game settings in Basic / Detailed / Advanced levels, difficulty presets and challenges
- World import (ZIP), config export / import (PC, server file, another server)
- Per-server quick actions, scheduler with in-game warnings, RAM limit, CPU pinning
- English + Czech UI, first-run password setup, 1-year sessions
- Docker image on GHCR, one-line installer, self-update via the host updater
- `7edcore` command line (status, save, stop-all, resume, …) for scripts and UPS software
- Graceful saves on shutdown on any machine; battery handling (7edcore-powerwatch) for laptops / mini PCs; NUT and apcupsd examples
