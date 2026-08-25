#!/usr/bin/env bash
# Print the current public URL of the tunnel.
#
# With a named tunnel (CF_TUNNEL_TOKEN set) the hostname is the one configured
# in the Cloudflare dashboard and never changes. With a quick tunnel the URL is
# random and changes every restart, so re-run this after each reboot.

set -uo pipefail
URL=$(sudo journalctl -u adhd-tunnel --since '-30d' --no-pager 2>/dev/null \
      | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)

if [ -n "$URL" ]; then
  echo "  Participants : $URL/test_list.html"
  echo "  Admin        : $URL/admin.html"
  echo
  echo "  (quick tunnel — this URL changes whenever adhd-tunnel restarts;"
  echo "   set CF_TUNNEL_TOKEN in deploy/adhd-games.env for a stable one)"
else
  echo "  No quick-tunnel URL in the logs."
  echo "  If you configured a named tunnel (CF_TUNNEL_TOKEN), the hostname is"
  echo "  the one you set in the Cloudflare Zero Trust dashboard."
  echo "  Otherwise check: sudo journalctl -u adhd-tunnel -n 50 --no-pager"
fi
