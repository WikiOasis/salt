#!/bin/bash
# Check authentik backup freshness — that a dump ran, and that it reached S3.
#
# This check is the difference between "we have backups" and "we had backups".
# The cron writes its output to a file nobody reads, so without this a dump that
# started failing in March is discovered during the restore.
#
# Usage: check_authentik_backup.sh [dump|upload] [state_dir]
MODE="${1:-dump}"
STATE_DIR="${2:-/srv/authentik/backups}"
S3_ENV=/etc/authentik-backup/s3.env
NOW=$(date +%s)

case "$MODE" in
    dump)
        MARKER="$STATE_DIR/last_backup"
        LABEL="dump"
        ;;
    upload)
        MARKER="$STATE_DIR/last_upload"
        LABEL="upload to S3"
        # Local-only is a supported configuration, so do not report a missing
        # upload as a failure when no bucket is configured to upload to --
        # otherwise this check sits CRITICAL forever on a working install.
        if [ -f "$S3_ENV" ]; then
            bucket=$(sed -n "s/^S3_BUCKET='\(.*\)'$/\1/p" "$S3_ENV")
        else
            bucket=""
        fi
        if [ -z "$bucket" ]; then
            echo "OK: no S3 bucket configured; dumps are local only"
            exit 0
        fi
        ;;
    *)
        echo "UNKNOWN: unknown mode '${MODE}'"
        exit 3
        ;;
esac

# Nightly job, so the thresholds match mariadb's daily incremental: one missed
# run warns, two are critical.
if [ ! -f "$MARKER" ]; then
    echo "CRITICAL: authentik backup ${LABEL} has never succeeded"
    exit 2
fi

MTIME=$(cat "$MARKER")
AGE_H=$(( (NOW - MTIME) / 3600 ))

if [ "$AGE_H" -ge 28 ]; then
    echo "CRITICAL: last authentik backup ${LABEL} was ${AGE_H}h ago (>28h) | age_hours=${AGE_H}"
    exit 2
elif [ "$AGE_H" -ge 26 ]; then
    echo "WARNING: last authentik backup ${LABEL} was ${AGE_H}h ago (>26h) | age_hours=${AGE_H}"
    exit 1
else
    echo "OK: last authentik backup ${LABEL} ${AGE_H}h ago | age_hours=${AGE_H}"
    exit 0
fi
