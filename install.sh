#!/bin/bash
# 7edCore installer - Linux x86_64 with systemd.
#   curl -fsSL https://raw.githubusercontent.com/Koberecnikos/7edCore/main/install.sh | sudo bash
# Re-running it is safe: it updates the updater and keeps your compose.yaml and data.
set -euo pipefail

REPO="${SEVENEDCORE_REPO:-Koberecnikos/7edCore}"
BRANCH="${SEVENEDCORE_BRANCH:-main}"
DIR="${SEVENEDCORE_DIR:-/opt/7edcore}"
RAW="https://raw.githubusercontent.com/$REPO/$BRANCH"

say() { printf '\033[1;31m7edCore\033[0m %s\n' "$*"; }
die() { say "ERROR: $*"; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root (sudo)"
[ "$(uname -m)" = x86_64 ] || die "7 Days to Die dedicated server needs an x86_64 machine"
command -v systemctl >/dev/null || die "systemd is required"
command -v curl >/dev/null || { apt-get update -qq && apt-get install -y -qq curl; }

if ! command -v docker >/dev/null; then
  say "installing Docker (get.docker.com)…"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null
docker compose version >/dev/null 2>&1 || die "docker compose plugin is missing"

say "installing to $DIR"
mkdir -p "$DIR/data"
chown 1000:1000 "$DIR/data"
if [ -f "$DIR/compose.yaml" ]; then
  say "keeping your existing compose.yaml"
else
  curl -fsSL "$RAW/deploy/compose.yaml" -o "$DIR/compose.yaml"
  tz=$(timedatectl show -p Timezone --value 2>/dev/null || true)
  [ -n "$tz" ] && echo "TZ=$tz" > "$DIR/.env"
fi
curl -fsSL "$RAW/deploy/7edcore-update" -o /usr/local/bin/7edcore-update
curl -fsSL "$RAW/deploy/7edcore" -o /usr/local/bin/7edcore
chmod +x /usr/local/bin/7edcore-update /usr/local/bin/7edcore
# containers need time to save the game servers when the host shuts down
mkdir -p /etc/systemd/system/docker.service.d
curl -fsSL "$RAW/deploy/docker-stop-timeout.conf" -o /etc/systemd/system/docker.service.d/7edcore-stop-timeout.conf
curl -fsSL "$RAW/deploy/7edcore-update.service" -o /etc/systemd/system/7edcore-update.service
curl -fsSL "$RAW/deploy/7edcore-update.timer" -o /etc/systemd/system/7edcore-update.timer
[ -f /etc/default/7edcore ] || printf 'SEVENEDCORE_DIR=%s\nSEVENEDCORE_DATA=%s/data\n' "$DIR" "$DIR" > /etc/default/7edcore
# power-loss handling for machines with a battery (laptop, mini PC with built-in UPS)
POWERWATCH="${SEVENEDCORE_POWERWATCH:-auto}"
if [ "$POWERWATCH" = auto ]; then
  POWERWATCH=0
  grep -qsx Mains /sys/class/power_supply/*/type && grep -qsx Battery /sys/class/power_supply/*/type && POWERWATCH=1
fi
if [ "$POWERWATCH" = 1 ]; then
  say "battery detected - enabling power-loss handling (7edcore-powerwatch)"
  curl -fsSL "$RAW/deploy/power/7edcore-powerwatch" -o /usr/local/bin/7edcore-powerwatch
  chmod +x /usr/local/bin/7edcore-powerwatch
  curl -fsSL "$RAW/deploy/power/7edcore-powerwatch.service" -o /etc/systemd/system/7edcore-powerwatch.service
  [ -f /etc/default/7edcore-powerwatch ] || curl -fsSL "$RAW/deploy/power/7edcore-powerwatch.default" -o /etc/default/7edcore-powerwatch
fi
systemctl daemon-reload
systemctl enable --now 7edcore-update.timer >/dev/null
[ "$POWERWATCH" = 1 ] && systemctl enable --now 7edcore-powerwatch.service >/dev/null

say "downloading and starting 7edCore…"
cd "$DIR"
docker compose pull -q
docker compose up -d

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  say "opening game ports in ufw (26900-26939 tcp/udp); the panel port 8120 stays LAN-only"
  ufw allow 26900:26939/tcp >/dev/null; ufw allow 26900:26939/udp >/dev/null
  ufw allow from 10.0.0.0/8 to any port 8120 proto tcp >/dev/null
  ufw allow from 172.16.0.0/12 to any port 8120 proto tcp >/dev/null
  ufw allow from 192.168.0.0/16 to any port 8120 proto tcp >/dev/null
  ufw allow from 100.64.0.0/10 to any port 8120 proto tcp >/dev/null
fi

if command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
  say "opening game ports in firewalld (26900-26939 tcp/udp)"
  firewall-cmd -q --permanent --add-port=26900-26939/tcp --add-port=26900-26939/udp
  firewall-cmd -q --reload
fi

ips=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9.]+$' | head -3)
echo
say "done. Open the panel and choose the admin password:"
for ip in $ips; do echo "    http://$ip:8120"; done
echo
echo "  data:     $DIR/data"
echo "  updates:  automatic (change in the panel: Panel → 7edCore updates)"
echo "  command:  7edcore status | save | stop-all | resume | update | logs"
echo "  game:     forward 26900-26903 TCP+UDP on your router for server 1 (26910… for server 2)"
