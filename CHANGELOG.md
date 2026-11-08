# Changelog

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
