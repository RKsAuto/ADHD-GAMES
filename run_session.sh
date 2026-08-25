#!/usr/bin/env bash
# Run a data-collection session from this machine and expose it on a public
# URL, so participants on any network can take the tests without any hosting.
#
#   ./run_session.sh
#
# Requires: python3, and cloudflared (auto-downloaded below if missing).
# Set MONGO_URI first if you want data in Atlas as well as the local file:
#   export MONGO_URI="mongodb+srv://...";  export EXPORT_KEY="yourkey"
#
# Keep this terminal (and the laptop) open for the whole session. Data is
# written to local_data.json here, and to MongoDB too when MONGO_URI is set.

set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-5000}"

# ── Dependencies ─────────────────────────────────────────────
if [ ! -d venv ]; then
  echo "Creating virtualenv..."
  python3 -m venv venv
fi
./venv/bin/pip install --quiet -r requirements.txt

# ── cloudflared (free public tunnel, no account needed) ──────
CF=./cloudflared
if ! command -v cloudflared >/dev/null 2>&1 && [ ! -x "$CF" ]; then
  echo "Downloading cloudflared..."
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64)  URL=https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 ;;
    Linux-aarch64) URL=https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 ;;
    Darwin-arm64)  URL=https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz ;;
    Darwin-x86_64) URL=https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz ;;
    *) echo "Unsupported platform. Install cloudflared manually: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"; exit 1 ;;
  esac
  if [[ "$URL" == *.tgz ]]; then
    curl -fsSL "$URL" -o cf.tgz && tar xzf cf.tgz cloudflared && rm cf.tgz
  else
    curl -fsSL "$URL" -o cloudflared
  fi
  chmod +x cloudflared
fi
command -v cloudflared >/dev/null 2>&1 && CF=cloudflared

# ── Start ────────────────────────────────────────────────────
echo
echo "Storage: ${MONGO_URI:+MongoDB + local file}${MONGO_URI:-local file only (MONGO_URI not set)}"
echo "Starting server on :$PORT ..."
./venv/bin/python server.py > session_server.log 2>&1 &
SERVER_PID=$!
trap 'echo; echo "Stopping..."; kill $SERVER_PID $TUNNEL_PID 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 || {
  echo "Server failed to start. Log:"; cat session_server.log; exit 1; }
echo "Server is up."

echo "Opening public tunnel..."
$CF tunnel --url "http://127.0.0.1:$PORT" > session_tunnel.log 2>&1 &
TUNNEL_PID=$!

PUBLIC=""
for _ in $(seq 1 60); do
  PUBLIC=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' session_tunnel.log | head -1 || true)
  [ -n "$PUBLIC" ] && break
  sleep 1
done
[ -n "$PUBLIC" ] || { echo "Tunnel did not start. Log:"; tail -20 session_tunnel.log; exit 1; }

cat <<EOF

──────────────────────────────────────────────────────────────
  SESSION IS LIVE

  Share with participants:
      $PUBLIC/test_list.html

  Your admin dashboard:
      $PUBLIC/admin.html
      ${EXPORT_KEY:+(export key: the EXPORT_KEY you set)}${EXPORT_KEY:-(no EXPORT_KEY set — the dashboard is open to anyone with the link)}

  Keep this window open until everyone has finished.
  Press Ctrl-C to end the session.
──────────────────────────────────────────────────────────────

EOF
wait $SERVER_PID
