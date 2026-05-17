#!/bin/bash
# Check HAProxy backends for DOWN servers via the stats socket.
SOCKET="${1:-/run/haproxy/admin.sock}"

if [ ! -S "$SOCKET" ]; then
    echo "CRITICAL: HAProxy stats socket not found at $SOCKET"
    exit 2
fi

stats=$(echo "show stat" | socat "$SOCKET" - 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$stats" ]; then
    echo "CRITICAL: Cannot read HAProxy stats"
    exit 2
fi

# Column 18 is the status field; skip header, FRONTEND, and BACKEND summary rows.
down=$(echo "$stats" | awk -F',' '
    /^#/ { next }
    $2 == "FRONTEND" || $2 == "BACKEND" { next }
    $18 == "DOWN" { print $1 "/" $2 }
')

total=$(echo "$stats" | awk -F',' '
    /^#/ { next }
    $2 == "FRONTEND" || $2 == "BACKEND" { next }
    { count++ }
    END { print count+0 }
')

if [ -z "$down" ]; then
    echo "OK: All $total backend server(s) up"
    exit 0
fi

down_count=$(echo "$down" | grep -c .)
down_list=$(echo "$down" | tr '\n' ' ')
echo "CRITICAL: $down_count/$total backend(s) DOWN: $down_list"
exit 2
