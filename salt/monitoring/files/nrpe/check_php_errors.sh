#!/bin/bash
# Check PHP-FPM error log for recent ERROR/WARNING messages.
LOG="${1:-/var/log/php8.4-fpm.log}"
WARN="${2:-5}"
CRIT="${3:-20}"
LINES=500

if [ ! -f "$LOG" ]; then
    echo "UNKNOWN: Log not found: $LOG"
    exit 3
fi

errors=$(tail -n "$LINES" "$LOG" | grep -cE '^\[.+\] (ERROR|WARNING)' 2>/dev/null || true)
errors=${errors:-0}

if [ "$errors" -ge "$CRIT" ]; then
    echo "CRITICAL: ${errors} PHP error(s) in last $LINES log lines (${LOG})"
    exit 2
elif [ "$errors" -ge "$WARN" ]; then
    echo "WARNING: ${errors} PHP error(s) in last $LINES log lines (${LOG})"
    exit 1
else
    echo "OK: ${errors} PHP error(s) in last $LINES log lines (${LOG})"
    exit 0
fi
