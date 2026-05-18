#!/bin/bash
# Check Redis is responding to PING.
HOST=${1:-127.0.0.1}
PORT=${2:-6379}

if ! command -v redis-cli &>/dev/null; then
    echo "UNKNOWN: redis-cli not found"
    exit 3
fi

result=$(redis-cli -h "$HOST" -p "$PORT" ping 2>&1)

if [ "$result" = "PONG" ]; then
    echo "OK: Redis on ${HOST}:${PORT} is responding"
    exit 0
else
    echo "CRITICAL: Redis on ${HOST}:${PORT} - ${result}"
    exit 2
fi