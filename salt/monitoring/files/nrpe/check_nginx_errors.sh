#!/bin/bash
# Check nginx HTTP error rate over the last N log lines.
# $4 = status class prefix to count: 4 for 4xx, 5 for 5xx (default 5)
LOG="${1:-/var/log/nginx/access.log}"
WARN_PCT="${2:-5}"
CRIT_PCT="${3:-15}"
CLASS="${4:-5}"
LINES=500

if [ ! -f "$LOG" ]; then
    echo "UNKNOWN: Log not found: $LOG"
    exit 3
fi

read -r errors total <<< "$(tail -n "$LINES" "$LOG" | awk -v class="$CLASS" '
    { total++ }
    substr($9, 1, 1) == class { errors++ }
    END { print errors+0, total+0 }
')"

if [ "$total" -eq 0 ]; then
    echo "OK: No requests in last $LINES log lines"
    exit 0
fi

pct=$(( errors * 100 / total ))

if [ "$pct" -ge "$CRIT_PCT" ]; then
    echo "CRITICAL: ${pct}% ${CLASS}xx errors ($errors/$total in last $LINES requests)"
    exit 2
elif [ "$pct" -ge "$WARN_PCT" ]; then
    echo "WARNING: ${pct}% ${CLASS}xx errors ($errors/$total in last $LINES requests)"
    exit 1
else
    echo "OK: ${pct}% ${CLASS}xx errors ($errors/$total in last $LINES requests)"
    exit 0
fi
