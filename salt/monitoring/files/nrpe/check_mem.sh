#!/bin/bash
# Check memory usage via /proc/meminfo.
# Uses MemAvailable which accounts for reclaimable cache/buffers.
WARNING=${1:-80}
CRITICAL=${2:-90}

read -r total available <<< "$(awk '
    /^MemTotal:/     { total = $2 }
    /^MemAvailable:/ { avail = $2 }
    END { print total+0, avail+0 }
' /proc/meminfo)"

if [ "$total" -eq 0 ]; then
    echo "UNKNOWN: Cannot read /proc/meminfo"
    exit 3
fi

used=$(( total - available ))
pct=$(( used * 100 / total ))
used_mb=$(( used / 1024 ))
total_mb=$(( total / 1024 ))

if [ "$pct" -ge "$CRITICAL" ]; then
    echo "CRITICAL: Memory ${pct}% used (${used_mb}MB/${total_mb}MB)"
    exit 2
elif [ "$pct" -ge "$WARNING" ]; then
    echo "WARNING: Memory ${pct}% used (${used_mb}MB/${total_mb}MB)"
    exit 1
else
    echo "OK: Memory ${pct}% used (${used_mb}MB/${total_mb}MB)"
    exit 0
fi
