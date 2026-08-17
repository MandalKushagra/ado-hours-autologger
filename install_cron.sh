#!/bin/bash
# Installs the cron job that runs the auto-logger every 15 min between 4-5 PM,
# Mon-Fri. The script self-locks so the actual update happens only once per day.
#
# Usage: ./install_cron.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/run_cron.sh"

CRON_LINE="*/15 16 * * 1-5 \"$WRAPPER\""
CRON_COMMENT="# Smart ADO hours auto-updater (self-locks to once/day)"

# Remove any prior entry pointing at this wrapper, then append fresh.
EXISTING="$(crontab -l 2>/dev/null | grep -v -F "$WRAPPER" | grep -v -F "$CRON_COMMENT" || true)"

{
  [ -n "$EXISTING" ] && echo "$EXISTING"
  echo "$CRON_COMMENT"
  echo "$CRON_LINE"
} | crontab -

echo "Cron installed:"
echo "  $CRON_LINE"
echo
echo "Verify with: crontab -l"
