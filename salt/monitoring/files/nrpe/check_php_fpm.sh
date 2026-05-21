#!/bin/bash
# Check PHP-FPM liveness and pool health via FastCGI socket.
# Requires: libfcgi-bin (provides cgi-fcgi)
SOCKET=${1:-/run/php/php8.4-fpm.sock}
QUEUE_WARN=${2:-5}
QUEUE_CRIT=${3:-10}

if ! command -v cgi-fcgi &>/dev/null; then
    echo "UNKNOWN: cgi-fcgi not found (install libfcgi-bin)"
    exit 3
fi

if [ ! -S "$SOCKET" ]; then
    echo "CRITICAL: PHP-FPM socket not found: ${SOCKET}"
    exit 2
fi

fcgi_get() {
    SCRIPT_NAME="$1" SCRIPT_FILENAME="$1" REQUEST_METHOD=GET \
        cgi-fcgi -bind -connect "$SOCKET" 2>&1
}

# Liveness — /ping must return "pong"
ping_result=$(fcgi_get /ping)
if ! echo "$ping_result" | grep -qi "pong"; then
    echo "CRITICAL: PHP-FPM not responding on ${SOCKET} - ${ping_result}"
    exit 2
fi

# Status — parse pool metrics
status_result=$(fcgi_get /status)

get_stat() {
    echo "$status_result" | grep -i "^${1}:" | awk '{print $NF}'
}

listen_queue=$(get_stat "listen queue")
max_children_reached=$(get_stat "max children reached")
slow_requests=$(get_stat "slow requests")
active=$(get_stat "active processes")
idle=$(get_stat "idle processes")

state=0
msgs=()

if [ -n "$listen_queue" ]; then
    if [ "$listen_queue" -ge "$QUEUE_CRIT" ]; then
        msgs+=("listen queue=${listen_queue} >= ${QUEUE_CRIT} (CRITICAL)")
        state=2
    elif [ "$listen_queue" -ge "$QUEUE_WARN" ]; then
        msgs+=("listen queue=${listen_queue} >= ${QUEUE_WARN} (WARNING)")
        [ "$state" -lt 1 ] && state=1
    fi
fi

if [ -n "$max_children_reached" ] && [ "$max_children_reached" -gt 0 ]; then
    msgs+=("max children reached=${max_children_reached} (WARNING)")
    [ "$state" -lt 1 ] && state=1
fi

if [ -n "$slow_requests" ] && [ "$slow_requests" -gt 0 ]; then
    msgs+=("slow requests=${slow_requests} (WARNING)")
    [ "$state" -lt 1 ] && state=1
fi

summary="active=${active:-?}, idle=${idle:-?}, queue=${listen_queue:-?}"

case "$state" in
    0) echo "OK: PHP-FPM ${SOCKET} - ${summary}";                          exit 0 ;;
    1) echo "WARNING: PHP-FPM ${SOCKET} - $(IFS=', '; echo "${msgs[*]}")"; exit 1 ;;
    2) echo "CRITICAL: PHP-FPM ${SOCKET} - $(IFS=', '; echo "${msgs[*]}")";exit 2 ;;
esac
