#!/bin/sh
# start a test panel: run_server.sh <datadir> <port>
D=$1; PORT=${2:-18200}; T=$(cd "$(dirname "$0")" && pwd)
pkill -f "PANEL_PORT_MARK=$PORT" 2>/dev/null
cd "$T/../app"
env PANEL_PORT_MARK=$PORT DATA_DIR=$D STEAMCMD=$T/fake/steamcmd.py PANEL_PORT=$PORT PANEL_PASSWORD=testpass123 GAME_PORT_BASE=36900 WEB_PORT_BASE=38080 python3 main.py
