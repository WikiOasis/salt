#!/bin/bash
# Check authentik backup freshness — that a dump ran, and that it reached S3.
#
# This check is the difference between "we have backups" and "we had backups".
# The cron writes its output to a file nobody reads, so without this a dump that
# started failing in March is discovered during the restore.
#
# Requires: sudoers entry for nagios to run this script as root -- both the
# dump marker under /srv/authentik/backups and /etc/authentik-backup/s3.env
# are root-only, and NRPE runs plugins as the unprivileged nagios user.
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

# Read the marker defensively. It is written with a plain `date +%s > file`, so
# a full disk or an interrupted write can leave it empty or half-written, and an
# unreadable file is possible too. Arithmetic on a value that is not a plain
# decimal integer fails, which leaves AGE_H empty, makes both threshold tests
# below error out, and falls through to the OK branch -- a corrupt marker would
# report success, which is the exact lie this check exists to catch. A leading
# zero is rejected with the rest: `date +%s` never emits one, and it would be
# read as octal and fail the same way.
MTIME=$(cat "$MARKER" 2>/dev/null)
case "$MTIME" in
    ''|*[!0-9]*|0*)
        echo "CRITICAL: authentik backup ${LABEL} marker ${MARKER} is unreadable or malformed"
        exit 2
        ;;
esac

AGE_H=$(( (NOW - MTIME) / 3600 ))

# A marker dated in the future is either clock skew or a bad write; the age is
# meaningless either way, and a negative one sits below both thresholds and so
# would read as a backup that just ran.
if [ "$AGE_H" -lt 0 ]; then
    echo "CRITICAL: authentik backup ${LABEL} marker ${MARKER} is dated in the future (${MTIME}); check the clock"
    exit 2
fi

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
