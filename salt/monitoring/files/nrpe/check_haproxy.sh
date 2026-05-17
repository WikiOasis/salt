#!/bin/bash
# Check HAProxy is alive via the stats socket.
SOCKET="${1:-/run/haproxy/admin.sock}"

if [ ! -S "$SOCKET" ]; then
    echo "CRITICAL: HAProxy stats socket not found at $SOCKET"
    exit 2
fi

info=$(echo "show info" | socat "$SOCKET" - 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$info" ]; then
    echo "CRITICAL: Cannot communicate with HAProxy via socket"
    exit 2
fi

uptime=$(echo "$info" | awk -F': ' '/^Uptime_sec:/{print $2}')
version=$(echo "$info" | awk -F': ' '/^Version:/{print $2}')
echo "OK: HAProxy $version running (uptime ${uptime}s)"
exit 0
