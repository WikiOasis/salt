#!/bin/bash
# Check available memory via /proc/meminfo.
#
# Thresholds are an ABSOLUTE amount of MemAvailable in MB, not a percentage: a
# percentage of a small host is not a useful signal (95% used of 4GB still
# leaves ~200MB of headroom, while 95% used of 64GB leaves ~3GB), so the alert
# is on how much room is actually left to allocate.
#
# MemAvailable is the kernel's own estimate of what a new workload can get
# without swapping, so it already accounts for reclaimable page cache and
# buffers.
#
# Usage: check_mem.sh [warn_mb] [crit_mb]   (warn/crit are "available below")
WARNING=${1:-512}
CRITICAL=${2:-256}
MEMINFO=${MEMINFO:-/proc/meminfo}

read -r total available <<< "$(awk '
    /^MemTotal:/     { total = $2 }
    /^MemAvailable:/ { avail = $2 }
    END { print total+0, avail+0 }
' "$MEMINFO" 2>/dev/null)"

if [ -z "$total" ] || [ "$total" -eq 0 ]; then
    echo "UNKNOWN: Cannot read ${MEMINFO}"
    exit 3
fi

used=$(( total - available ))
pct=$(( used * 100 / total ))
avail_mb=$(( available / 1024 ))
used_mb=$(( used / 1024 ))
total_mb=$(( total / 1024 ))

perf="mem_available=${avail_mb}MB;${WARNING};${CRITICAL};0;${total_mb}"
perf="${perf} mem_used_pct=${pct}%;;;0;100"
detail="${avail_mb}MB available, ${pct}% used (${used_mb}MB/${total_mb}MB)"

if [ "$avail_mb" -lt "$CRITICAL" ]; then
    echo "CRITICAL: ${detail} | ${perf}"
    exit 2
elif [ "$avail_mb" -lt "$WARNING" ]; then
    echo "WARNING: ${detail} | ${perf}"
    exit 1
else
    echo "OK: ${detail} | ${perf}"
    exit 0
fi
