#!/bin/bash
# Check MariaDB backup freshness and binlog stream health.
# Usage: check_mariadb_backup.sh [base|incremental|binlog]
STATE_DIR=/var/backups/mariadb
LAST_FULL="$STATE_DIR/last_full_backup"
LAST_BACKUP="$STATE_DIR/last_backup"
BINLOG_DIR="$STATE_DIR/binlogs"
NOW=$(date +%s)

MODE="${1:-base}"

case "$MODE" in
    base)
        # warn > 8 days, crit > 9 days
        if [ ! -f "$LAST_FULL" ]; then
            echo "CRITICAL: no full backup has ever run"
            exit 2
        fi
        MTIME=$(cat "$LAST_FULL")
        AGE_H=$(( (NOW - MTIME) / 3600 ))
        if [ "$AGE_H" -ge 216 ]; then
            echo "CRITICAL: full backup is ${AGE_H}h old (>9d) | age_hours=${AGE_H}"
            exit 2
        elif [ "$AGE_H" -ge 192 ]; then
            echo "WARNING: full backup is ${AGE_H}h old (>8d) | age_hours=${AGE_H}"
            exit 1
        else
            echo "OK: full backup ${AGE_H}h old | age_hours=${AGE_H}"
            exit 0
        fi
        ;;

    incremental)
        # warn > 26h, crit > 28h
        if [ ! -f "$LAST_BACKUP" ]; then
            echo "CRITICAL: no backup has ever run"
            exit 2
        fi
        MTIME=$(cat "$LAST_BACKUP")
        AGE_H=$(( (NOW - MTIME) / 3600 ))
        if [ "$AGE_H" -ge 28 ]; then
            echo "CRITICAL: last backup is ${AGE_H}h old (>28h) | age_hours=${AGE_H}"
            exit 2
        elif [ "$AGE_H" -ge 26 ]; then
            echo "WARNING: last backup is ${AGE_H}h old (>26h) | age_hours=${AGE_H}"
            exit 1
        else
            echo "OK: last backup ${AGE_H}h old | age_hours=${AGE_H}"
            exit 0
        fi
        ;;

    binlog)
        # service must be active; newest binlog file must be < 15min old (warn) / 30min (crit)
        if ! systemctl is-active --quiet mariadb-binlog-stream; then
            STATUS=$(systemctl is-active mariadb-binlog-stream 2>&1)
            echo "CRITICAL: mariadb-binlog-stream is ${STATUS}"
            exit 2
        fi
        LATEST=$(ls -t "$BINLOG_DIR"/mysql-bin.[0-9]* 2>/dev/null | head -1)
        if [ -z "$LATEST" ]; then
            echo "WARNING: service running but no binlog files yet"
            exit 1
        fi
        MTIME=$(stat -c %Y "$LATEST")
        AGE_M=$(( (NOW - MTIME) / 60 ))
        if [ "$AGE_M" -ge 30 ]; then
            echo "CRITICAL: newest binlog is ${AGE_M}min old (>30min) | age_minutes=${AGE_M}"
            exit 2
        elif [ "$AGE_M" -ge 15 ]; then
            echo "WARNING: newest binlog is ${AGE_M}min old (>15min) | age_minutes=${AGE_M}"
            exit 1
        else
            echo "OK: binlog stream active, newest file ${AGE_M}min old | age_minutes=${AGE_M}"
            exit 0
        fi
        ;;

    *)
        echo "UNKNOWN: invalid mode '${MODE}' — use base|incremental|binlog"
        exit 3
        ;;
esac
