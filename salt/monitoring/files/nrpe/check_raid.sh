#!/bin/bash
# Check mdadm software RAID array health via /proc/mdstat.

MDSTAT=/proc/mdstat

if [ ! -f "$MDSTAT" ]; then
  echo "UNKNOWN: $MDSTAT not found"
  exit 3
fi

ARRAYS=$(grep "^md" "$MDSTAT" | awk '{print $1}')

if [ -z "$ARRAYS" ]; then
  echo "OK: no mdadm arrays configured"
  exit 0
fi

FAILED=()
DEGRADED=()
OK=()

for array in $ARRAYS; do
  line=$(grep "^$array " "$MDSTAT")
  # Active drives vs total: e.g. [2/1] means 2 expected, 1 active → degraded
  total=$(echo "$line" | grep -oP '\[\K[0-9]+(?=/)')
  active=$(echo "$line" | grep -oP '/\K[0-9]+(?=\])')

  if echo "$line" | grep -q "_"; then
    FAILED+=("$array")
  elif [ -n "$total" ] && [ -n "$active" ] && [ "$active" -lt "$total" ]; then
    DEGRADED+=("$array")
  else
    OK+=("$array")
  fi
done

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "CRITICAL: RAID arrays with failed members: ${FAILED[*]}"
  exit 2
elif [ ${#DEGRADED[@]} -gt 0 ]; then
  echo "WARNING: RAID arrays degraded: ${DEGRADED[*]}"
  exit 1
else
  echo "OK: all RAID arrays healthy (${OK[*]})"
  exit 0
fi
