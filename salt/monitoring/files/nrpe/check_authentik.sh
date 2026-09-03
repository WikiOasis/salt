#!/bin/bash
# Check authentik answers on its readiness endpoint.
#
# /-/health/ready/ is the useful one of the two health endpoints: it returns 2xx
# only once the server has a working database connection, so it fails while the
# stack is migrating, when Postgres is down, and when the container is looping.
# /-/health/live/ answers as soon as the process is up and would call all three
# of those healthy.
HOST=${1:-127.0.0.1}
PORT=${2:-9000}
URL="http://${HOST}:${PORT}/-/health/ready/"

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$URL" 2>/dev/null) || code=000

case "$code" in
    2??)
        echo "OK: authentik ready (HTTP ${code})"
        exit 0
        ;;
    000)
        echo "CRITICAL: authentik unreachable at ${URL}"
        exit 2
        ;;
    *)
        echo "CRITICAL: authentik returned HTTP ${code} from ${URL}"
        exit 2
        ;;
esac
