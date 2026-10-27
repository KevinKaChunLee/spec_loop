#!/usr/bin/env bash
# Create the loop's Docker network if needed and let its containers open connections only to the
# model servers: no PyPI, no GitHub, no upstream fix to download.
#
#   sudo swe/setup/egress.sh                          # the endpoints in swe_config.json
#   sudo swe/setup/egress.sh 10.0.0.5:30000 10.0.0.5:30001
#
# The rules go into Docker's DOCKER-USER chain (forwarded traffic), tagged "swe-loop", and are
# replaced on every run; run it again after a reboot. `swe_loop.py check --image ...` verifies them.
# Traffic to the Docker host itself is not forwarded: when SGLang runs on this host, containers
# reach it at the network's gateway address (printed below), and only the INPUT chain and SGLang's
# --api-key restrict that. IPv4 only, as Docker networks are by default.
set -euo pipefail
cd "$(dirname "$0")/../.."
NET=$(python3 -c 'import json; print(json.load(open("swe_config.json"))["docker"]["network"])')
if [ $# -gt 0 ]; then
  ENDPOINTS=("$@")
else
  mapfile -t ENDPOINTS < <(python3 - <<'EOF'
import json, urllib.parse
c = json.load(open("swe_config.json"))
urls = {c["server"]["base_url"]} | {m["base_url"] for m in c["models"].values() if m.get("base_url")}
for u in sorted(urls):
    p = urllib.parse.urlsplit(u)
    print(f"{p.hostname}:{p.port or (443 if p.scheme == 'https' else 80)}")
EOF
)
fi

docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
SUBNET=$(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}' "$NET" | awk '{print $1}')
GATEWAY=$(docker network inspect -f '{{range .IPAM.Config}}{{.Gateway}} {{end}}' "$NET" | awk '{print $1}')

while rule=$(iptables -S DOCKER-USER | grep -m1 -- '--comment swe-loop'); do
  eval "iptables ${rule/-A /-D }"
done
iptables -I DOCKER-USER 1 -s "$SUBNET" -m comment --comment swe-loop -j DROP
for ep in "${ENDPOINTS[@]}"; do
  host=${ep%:*} port=${ep##*:}
  ips=$(getent ahostsv4 "$host" | awk '{print $1}' | sort -u)
  [ -n "$ips" ] || { echo "cannot resolve $host" >&2; exit 1; }
  for ip in $ips; do
    iptables -I DOCKER-USER 1 -s "$SUBNET" -d "$ip" -p tcp --dport "$port" -m comment --comment swe-loop -j ACCEPT
  done
done
iptables -I DOCKER-USER 1 -s "$SUBNET" -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment swe-loop -j ACCEPT

echo "network $NET ($SUBNET, gateway $GATEWAY): outbound only to ${ENDPOINTS[*]}"
iptables -S DOCKER-USER | grep -- 'swe-loop'
