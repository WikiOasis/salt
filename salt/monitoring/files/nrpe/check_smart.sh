#!/bin/bash
# Check SMART health for all detected block devices.
# Uses smartctl exit codes (reliable across HDD/SSD/NVMe) rather than text parsing.
#   bit 1 (2):  device open failed
#   bit 3 (8):  SMART not supported / read failed
#   bit 5 (32): SMART status BAD (pre-fail or failed)
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
  sudo "$SMARTCTL" -H "/dev/$drive" > /dev/null 2>&1
  rc=$?
  if (( rc & 32 )); then
    FAILED+=("$drive")
  elif (( rc & 10 )); then
    UNKNOWN+=("$drive")
  else
    OK+=("$drive")
  fi
done

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "CRITICAL: SMART failure on: ${FAILED[*]}"
  exit 2
elif [ ${#UNKNOWN[@]} -gt 0 ]; then
  echo "UNKNOWN: cannot read SMART data for: ${UNKNOWN[*]}"
  exit 3
else
  echo "OK: all drives healthy (${OK[*]})"
  exit 0
fi
