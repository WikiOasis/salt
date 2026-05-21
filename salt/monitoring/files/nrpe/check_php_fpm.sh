#!/bin/bash
# Check PHP-FPM is responding by sending a ping via the FastCGI socket.
# Requires: libfcgi-bin (provides cgi-fcgi)
SOCKET=${1:-/run/php/php8.3-fpm.sock}

if ! command -v cgi-fcgi &>/dev/null; then
    echo "UNKNOWN: cgi-fcgi not found (install libfcgi-bin)"
    exit 3
fi

if [ ! -S "$SOCKET" ]; then
    echo "CRITICAL: PHP-FPM socket not found: ${SOCKET}"
    exit 2
fi

result=$(SCRIPT_NAME=/ping SCRIPT_FILENAME=/ping REQUEST_METHOD=GET \
    cgi-fcgi -bind -connect "$SOCKET" 2>&1)

if echo "$result" | grep -qi "pong"; then
    echo "OK: PHP-FPM responding on ${SOCKET}"
    exit 0
else
    echo "CRITICAL: PHP-FPM not responding on ${SOCKET} - ${result}"
    exit 2
fi
