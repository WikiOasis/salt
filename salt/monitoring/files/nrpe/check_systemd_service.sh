#!/bin/bash
# Check a systemd service unit is active.
SERVICE=${1:-}

if [ -z "$SERVICE" ]; then
    echo "UNKNOWN: No service name provided"
    exit 3
fi

status=$(systemctl is-active "$SERVICE" 2>&1)

case "$status" in
    active)
        echo "OK: ${SERVICE} is active"
        exit 0
        ;;
    inactive)
        echo "CRITICAL: ${SERVICE} is inactive"
        exit 2
        ;;
    failed)
        echo "CRITICAL: ${SERVICE} is failed"
        exit 2
        ;;
    *)
        echo "UNKNOWN: ${SERVICE} status is '${status}'"
        exit 3
        ;;
esac