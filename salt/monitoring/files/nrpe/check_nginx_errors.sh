#!/bin/bash
# Check nginx 5xx error rate over the last N log lines.
LOG="${1:-/var/log/nginx/access.log}"
WARN_PCT="${2:-5}"
CRIT_PCT="${3:-15}"
LINES=500

if [ ! -f "$LOG" ]; then
    echo "UNKNOWN: Log not found: $LOG"
    exit 3
fi

read -r errors total <<< "$(tail -n "$LINES" "$LOG" | awk '
    { total++ }
    $9 ~ /^5/ { errors++ }
    END { print errors+0, total+0 }
')"

if [ "$total" -eq 0 ]; then
    echo "OK: No requests in last $LINES log lines"
    exit 0
fi

pct=$(( errors * 100 / total ))

if [ "$pct" -ge "$CRIT_PCT" ]; then
    echo "CRITICAL: ${pct}% 5xx errors ($errors/$total in last $LINES requests)"
    exit 2
elif [ "$pct" -ge "$WARN_PCT" ]; then
    echo "WARNING: ${pct}% 5xx errors ($errors/$total in last $LINES requests)"
    exit 1
else
    echo "OK: ${pct}% 5xx errors ($errors/$total in last $LINES requests)"
    exit 0
fi
