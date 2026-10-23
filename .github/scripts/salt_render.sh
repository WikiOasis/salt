#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cp -r "$repo/pillar" "$work/pillar"
for example in "$work"/pillar/private/*.example; do
    cp "$example" "${example%.example}"
done
mkdir -p "$work/root"

cat > "$work/minion" <<CONF
root_dir: $work/root
file_client: local
file_roots:
  base:
    - $repo/salt
pillar_roots:
  base:
    - $work/pillar
grains:
  os: Debian
  os_family: Debian
  oscodename: ${OSCODENAME:-bookworm}
  osrelease: '12'
  osmajorrelease: 12
  osfinger: Debian-12
  kernel: Linux
  init: systemd
  cpuarch: x86_64
  osarch: amd64
  num_cpus: 4
  mem_total: 8192
  ipv4: [10.0.0.10]
  fqdn_ip4: [10.0.0.10]
  ip4_interfaces: {eth0: [10.0.0.10]}
  ip_interfaces: {eth0: [10.0.0.10]}
CONF

minions=(
    mw-us-east-011
    staging-us-east-011
    task-us-east-011
    apps-us-east-011
    auth-us-east-011
    bastion-us-east-011
    db-other-us-east-011
    db-pc-us-east-011
    db-c1-us-east-021
    proxy-us-east-011
    monitoring-us-east-021
    salt-us-east-011
    opensearch-us-east-011
    redis-us-east-011
    redis-us-east-012
    redis-us-east-021
    metal-us-east-01
    metal-us-east-02
)

failed=0
for minion in "${minions[@]}"; do
    for func in state.show_highstate state.show_lowstate; do
        out="$work/$minion.$func.json"
        if ! salt-call --local --config-dir="$work" -l quiet --id "$minion" "$func" --out=json > "$out" 2> "$work/err"; then
            echo "::error::$minion $func exited non-zero"
            cat "$work/err" "$out" || true
            failed=1
            continue
        fi
        if ! python3 - "$out" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1]))["local"]
if isinstance(data, list) and data and all(isinstance(item, str) for item in data):
    print("\n".join(data))
    sys.exit(1)
if not data:
    print("rendered nothing")
    sys.exit(1)
PY
        then
            echo "::error::$minion $func failed"
            failed=1
        fi
    done
    echo "rendered $minion"
done

exit "$failed"
