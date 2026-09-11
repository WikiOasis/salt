#!/bin/bash
# Check available memory via /proc/meminfo.
#
# The alert fires on whichever threshold is SMALLER: an absolute amount of
# MemAvailable in MB, or a percentage of MemTotal.
#
#   warn when available < min(warn_mb, warn_pct% of MemTotal)
#   crit when available < min(crit_mb, crit_pct% of MemTotal)
#
# Either term alone is wrong at one end of the fleet. A pure percentage of a
# big host alerts far too early (10% of 64GB is ~6.5GB of headroom, which is
# plenty), while a pure absolute floor alerts on a small host that is idle and
# healthy (512MB is half the RAM of a 1GB proxy, so it never clears). Taking
# the minimum keeps the absolute floor on big hosts and scales it down on
# small ones.
#
# MemAvailable is the kernel's own estimate of what a new workload can get
# without swapping, so it already accounts for reclaimable page cache and
# buffers.
#
# Usage: check_mem.sh [warn_mb] [crit_mb] [warn_pct] [crit_pct]
#        (thresholds are all "available below")
WARNING_MB=${1:-512}
CRITICAL_MB=${2:-256}
WARNING_PCT=${3:-10}
CRITICAL_PCT=${4:-5}
MEMINFO=${MEMINFO:-/proc/meminfo}

read -r total available have_available <<< "$(awk '
    /^MemTotal:/     { total = $2 }
    /^MemAvailable:/ { avail = $2; have_avail = 1 }
    END { print total+0, avail+0, have_avail+0 }
' "$MEMINFO" 2>/dev/null)"

if [ -z "$total" ] || [ "$total" -eq 0 ]; then
    echo "UNKNOWN: Cannot read ${MEMINFO}"
    exit 3
fi

# An absent MemAvailable field (kernels before 3.14) extracts as 0, which is
# indistinguishable from a host genuinely out of memory; report UNKNOWN rather
# than a permanent false CRITICAL.
if [ "$have_available" != "1" ]; then
    echo "UNKNOWN: ${MEMINFO} has no MemAvailable field"
    exit 3
fi

used=$(( total - available ))
pct=$(( used * 100 / total ))
avail_mb=$(( available / 1024 ))
used_mb=$(( used / 1024 ))
total_mb=$(( total / 1024 ))

# Integer arithmetic only: the percentage terms truncate downwards, which
# errs towards alerting slightly later rather than slightly earlier.
warn_pct_mb=$(( total_mb * WARNING_PCT / 100 ))
crit_pct_mb=$(( total_mb * CRITICAL_PCT / 100 ))

warn=$WARNING_MB
[ "$warn_pct_mb" -lt "$warn" ] && warn=$warn_pct_mb
crit=$CRITICAL_MB
[ "$crit_pct_mb" -lt "$crit" ] && crit=$crit_pct_mb

# Perfdata ranges are the EFFECTIVE thresholds for this host, not the raw
# floors, so graphs and the Nagios UI show the line the check actually used.
# "512:" is the Nagios range for "alert below 512".
perf="mem_available=${avail_mb}MB;${warn}:;${crit}:;0;${total_mb}"
perf="${perf} mem_used_pct=${pct}%;;;0;100"
detail="${avail_mb}MB available, ${pct}% used (${used_mb}MB/${total_mb}MB)"
detail="${detail}, thresholds ${warn}MB/${crit}MB"

if [ "$avail_mb" -lt "$crit" ]; then
    echo "CRITICAL: ${detail} | ${perf}"
    exit 2
elif [ "$avail_mb" -lt "$warn" ]; then
    echo "WARNING: ${detail} | ${perf}"
    exit 1
else
    echo "OK: ${detail} | ${perf}"
    exit 0
fi
