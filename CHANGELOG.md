# Changelog

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
