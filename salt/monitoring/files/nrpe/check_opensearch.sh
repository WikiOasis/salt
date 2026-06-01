#!/bin/bash
# Check OpenSearch cluster health via the HTTP API.
HOST="${1:-localhost}"
PORT="${2:-9200}"

response=$(curl -s --max-time 10 "http://${HOST}:${PORT}/_cluster/health" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$response" ]; then
    echo "CRITICAL: Cannot reach OpenSearch at ${HOST}:${PORT}"
    exit 2
fi

status=$(echo "$response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
nodes=$(echo "$response" | grep -o '"number_of_nodes":[0-9]*' | cut -d':' -f2)
cluster=$(echo "$response" | grep -o '"cluster_name":"[^"]*"' | cut -d'"' -f4)

case "$status" in
    green)
        echo "OK: OpenSearch cluster '${cluster}' is green (${nodes} nodes)"
        exit 0
        ;;
    yellow)
        echo "WARNING: OpenSearch cluster '${cluster}' is yellow (${nodes} nodes)"
        exit 1
        ;;
    red)
        echo "CRITICAL: OpenSearch cluster '${cluster}' is red (${nodes} nodes)"
        exit 2
        ;;
    *)
        echo "UNKNOWN: OpenSearch returned unexpected status: ${status:-no response}"
        exit 3
        ;;
esac