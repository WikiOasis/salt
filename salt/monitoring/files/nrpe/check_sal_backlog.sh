#!/bin/bash
WARN=${1:-20}
CRIT=${2:-100}
URL=${SAL_HEALTH_URL:-http://salt-us-east-021.ovvin.wonet:8740/healthz}

body=$(curl -fsS --max-time 10 "$URL" 2>&1) || { echo "CRITICAL: SAL health endpoint unreachable: ${body}"; exit 2; }

python3 - "$WARN" "$CRIT" "$body" <<'PY'
import json, sys
warn, crit, raw = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
try:
    h = json.loads(raw)
except ValueError:
    print("UNKNOWN: SAL health endpoint returned non-JSON")
    sys.exit(3)
pending = max(h.get("wiki_pending", 0), h.get("phorge_pending", 0))
failed = h.get("wiki_failed", 0) + h.get("phorge_failed", 0)
perf = "|wiki_pending={wiki_pending} wiki_failed={wiki_failed} phorge_pending={phorge_pending} phorge_failed={phorge_failed}".format(
    **{k: h.get(k, 0) for k in ("wiki_pending", "wiki_failed", "phorge_pending", "phorge_failed")})
summary = "wiki {} pending/{} failed, phorge {} pending/{} failed".format(
    h.get("wiki_pending", 0), h.get("wiki_failed", 0), h.get("phorge_pending", 0), h.get("phorge_failed", 0))
if pending >= crit:
    print("CRITICAL: SAL backlog: " + summary + perf); sys.exit(2)
if pending >= warn or failed:
    print("WARNING: SAL backlog: " + summary + perf); sys.exit(1)
print("OK: SAL " + summary + perf)
PY
