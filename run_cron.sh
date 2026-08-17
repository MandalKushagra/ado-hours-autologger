#!/bin/bash
# Cron wrapper for smart_ado_hours.py
# Sets up GUI env vars so notify-send popups work from cron's minimal environment.
#
# This script auto-detects its own location, so it works no matter where you
# clone the repo. Point your crontab at THIS file.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Required for desktop notifications from cron (Linux / GNOME)
export DISPLAY="${DISPLAY:-:0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

cd "$SCRIPT_DIR" || exit 1
mkdir -p logs
/usr/bin/env python3 smart_ado_hours.py >> logs/hours_cron.log 2>&1
