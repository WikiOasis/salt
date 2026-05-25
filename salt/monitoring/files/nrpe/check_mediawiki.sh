#!/bin/bash
# Check MediaWiki renders correctly by curling localhost with a virtual host header.
HOST="${1:-test.wikioasis.org}"
WARN_MS="${2:-3000}"
CRIT_MS="${3:-8000}"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

start_ms=$(date +%s%3N)
http_code=$(curl -sS \
    --max-time $(( (CRIT_MS + 999) / 1000 + 1 )) \
    --location \
    --resolve "${HOST}:80:127.0.0.1" \
    -o "$tmp" \
    -w "%{http_code}" \
    "http://${HOST}/" 2>&1)
curl_exit=$?
elapsed_ms=$(( $(date +%s%3N) - start_ms ))

if [ "$curl_exit" -ne 0 ]; then
    echo "CRITICAL: curl failed (exit ${curl_exit}) — Host: ${HOST}"
    exit 2
fi

if [ "$http_code" != "200" ]; then
    echo "CRITICAL: HTTP ${http_code} from localhost (Host: ${HOST})"
    exit 2
fi

if ! grep -qi 'mediawiki' "$tmp" 2>/dev/null; then
    echo "CRITICAL: HTTP 200 but no MediaWiki content detected (Host: ${HOST})"
    exit 2
fi

if [ "$elapsed_ms" -ge "$CRIT_MS" ]; then
    echo "CRITICAL: MediaWiki rendered but too slow (${elapsed_ms}ms) — HTTP ${http_code} (Host: ${HOST})"
    exit 2
elif [ "$elapsed_ms" -ge "$WARN_MS" ]; then
    echo "WARNING: MediaWiki rendered but slow (${elapsed_ms}ms) — HTTP ${http_code} (Host: ${HOST})"
    exit 1
fi

echo "OK: MediaWiki rendered in ${elapsed_ms}ms — HTTP ${http_code} (Host: ${HOST})"
exit 0