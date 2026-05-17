#!/bin/bash
# Check SMART health for all detected block devices.
# Requires: smartmontools, sudoers entry for nagios to run smartctl.

SMARTCTL=/usr/sbin/smartctl
DRIVES=$(lsblk -d -n -o NAME,TYPE | awk '$2=="disk"{print $1}')

if [ -z "$DRIVES" ]; then
  echo "UNKNOWN: no block devices found"
  exit 3
fi

FAILED=()
UNKNOWN=()
OK=()

for drive in $DRIVES; do
  result=$(sudo "$SMARTCTL" -H "/dev/$drive" 2>&1)
  if echo "$result" | grep -qE "PASSED|OK"; then
    OK+=("$drive")
  elif echo "$result" | grep -q "FAILED"; then
    FAILED+=("$drive")
  else
    UNKNOWN+=("$drive")
  fi
done

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "CRITICAL: SMART failure on: ${FAILED[*]}"
  exit 2
elif [ ${#UNKNOWN[@]} -gt 0 ]; then
  echo "UNKNOWN: cannot determine SMART status for: ${UNKNOWN[*]}"
  exit 3
else
  echo "OK: all drives healthy (${OK[*]})"
  exit 0
fi
