#!/usr/bin/env bash
# One-shot setup to run ADHD Cognitive Games on a Raspberry Pi (or any Linux
# box with systemd), exposed to the internet through a Cloudflare tunnel.
#
#   git clone <repo> && cd ADHD-GAMES
#   ./deploy/pi-setup.sh
#
# Installs a virtualenv, writes deploy/adhd-games.env, and enables two systemd
# services that start on boot and restart after crashes or power cuts:
#   adhd-games    gunicorn on 127.0.0.1:PORT (not exposed directly)
#   adhd-tunnel   cloudflared, publishing it to the world over HTTPS
#
# The tunnel means no port forwarding, no static IP and no router changes, and
# it works behind CGNAT. Only this app is published — not the rest of your
# network, and not SSH.

set -euo pipefail
cd "$(dirname "$0")/.."
APPDIR="$(pwd)"
USER_NAME="${SUDO_USER:-$(id -un)}"
PORT="${PORT:-5000}"
ENV_FILE="$APPDIR/deploy/adhd-games.env"

echo "App directory : $APPDIR"
echo "Service user  : $USER_NAME"
echo "Internal port : $PORT"
echo

# ── System packages ──────────────────────────────────────────
if command -v apt-get >/dev/null 2>&1; then
  echo "Installing system packages..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv python3-pip curl
fi

# ── Python environment ───────────────────────────────────────
echo "Setting up virtualenv..."
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt gunicorn

# ── Configuration ────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  echo
  echo "Configuration (press Enter to skip any of these):"
  read -rp "  MongoDB connection string (MONGO_URI): " MONGO_URI_IN
  read -rp "  Admin export key (EXPORT_KEY): " EXPORT_KEY_IN
  read -rp "  Cloudflare named-tunnel token, for a stable URL (CF_TUNNEL_TOKEN): " CF_TOKEN_IN
  umask 077                       # the file holds credentials
  cat > "$ENV_FILE" <<EOF
# Credentials for the ADHD Cognitive Games service. Keep this file private.
MONGO_URI=${MONGO_URI_IN}
EXPORT_KEY=${EXPORT_KEY_IN}
CF_TUNNEL_TOKEN=${CF_TOKEN_IN}
# The Pi is always on, so no keep-awake pinging is needed.
SELF_PING_MINUTES=0
EOF
  echo "Wrote $ENV_FILE"
else
  echo "Using existing $ENV_FILE"
fi

# ── cloudflared ──────────────────────────────────────────────
if command -v cloudflared >/dev/null 2>&1; then
  CFBIN="$(command -v cloudflared)"
else
  echo "Installing cloudflared..."
  case "$(uname -m)" in
    aarch64|arm64) ARCH=arm64 ;;
    armv7l|armv6l) ARCH=arm ;;
    x86_64)        ARCH=amd64 ;;
    *) echo "Unsupported architecture $(uname -m)"; exit 1 ;;
  esac
  sudo curl -fsSL -o /usr/local/bin/cloudflared \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}"
  sudo chmod +x /usr/local/bin/cloudflared
  CFBIN=/usr/local/bin/cloudflared
fi
echo "cloudflared: $CFBIN"

# ── systemd services ─────────────────────────────────────────
echo "Installing systemd services..."
for unit in adhd-games adhd-tunnel; do
  sed -e "s|__APPDIR__|$APPDIR|g" \
      -e "s|__USER__|$USER_NAME|g" \
      -e "s|__PORT__|$PORT|g" \
      -e "s|__CFBIN__|$CFBIN|g" \
      "$APPDIR/deploy/$unit.service" | sudo tee "/etc/systemd/system/$unit.service" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now adhd-games adhd-tunnel

sleep 5
echo
if systemctl is-active --quiet adhd-games; then
  echo "adhd-games:  running"
  curl -fsS "http://127.0.0.1:$PORT/healthz" && echo
else
  echo "adhd-games FAILED — logs:"; sudo journalctl -u adhd-games -n 30 --no-pager; exit 1
fi
systemctl is-active --quiet adhd-tunnel && echo "adhd-tunnel: running" || {
  echo "adhd-tunnel FAILED — logs:"; sudo journalctl -u adhd-tunnel -n 30 --no-pager; }

echo
echo "Public URL:"
"$APPDIR/deploy/tunnel-url.sh" || true
cat <<EOF

Both services start automatically on boot.
  Status : sudo systemctl status adhd-games adhd-tunnel
  Logs   : sudo journalctl -u adhd-games -f
  URL    : ./deploy/tunnel-url.sh
  Update : git pull && sudo systemctl restart adhd-games
EOF
