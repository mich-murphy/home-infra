#!/usr/bin/env bash
set -euo pipefail
: "${KUBECONFIG:?}" "${PROOF_CONTEXT:?}" "${PROOF_API_SERVER:?}"
[[ "${PROOF_TESTS_AUTHORIZED:-}" == yes ]] || { echo 'Explicit authorization required' >&2; exit 1; }
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
python3 "$ROOT/kubernetes/bootstrap/proof_guard.py"
K=(python3 "$ROOT/kubernetes/bootstrap/proof_guard.py" --context "$PROOF_CONTEXT")
[[ $("${K[@]}" config view --minify -o jsonpath='{.clusters[0].cluster.server}') == "$PROOF_API_SERVER" ]]
"${K[@]}" apply -k "$ROOT/kubernetes/platform/validation"
cleanup() {
 "${K[@]}" -n proof-network-test scale deploy/fixture deploy/denied-client --replicas=0
 "${K[@]}" -n proof-validation scale deploy/client --replicas=0
}
trap cleanup EXIT
"${K[@]}" -n proof-network-test scale deploy/fixture deploy/denied-client --replicas=1
"${K[@]}" -n proof-validation scale deploy/client --replicas=1
for d in fixture denied-client; do "${K[@]}" -n proof-network-test rollout status "deploy/$d" --timeout=180s; done
"${K[@]}" -n proof-validation rollout status deploy/client --timeout=180s
nonce="synthetic-proof-$(date -u +%Y%m%dT%H%M%SZ)"
# shellcheck disable=SC2016 # $1 expands inside the remote pod shell, not locally.
"${K[@]}" -n proof-network-test exec deploy/fixture -- sh -c 'printf "%s\n" "$1" > /data/www/index.html; sync' sh "$nonce"
fetch() { "${K[@]}" -n proof-validation exec deploy/client -- wget -q -T 5 -O - http://fixture.proof-network-test.svc.cluster.local:8080/; }
[[ $(fetch) == "$nonce" ]]; echo 'PASS DNS + explicitly allowed cross-namespace HTTP + volume write/read'
before=$("${K[@]}" -n proof-network-test get pods -l app=fixture -o jsonpath='{.items[0].metadata.uid}')
"${K[@]}" -n proof-network-test rollout restart deploy/fixture
"${K[@]}" -n proof-network-test rollout status deploy/fixture --timeout=180s
after=$("${K[@]}" -n proof-network-test get pods -l app=fixture -o json | python3 -c 'import json,sys; print(next(p["metadata"]["uid"] for p in json.load(sys.stdin)["items"] if not p["metadata"].get("deletionTimestamp")))')
[[ "$before" != "$after" ]]
[[ $(fetch) == "$nonce" ]]; echo "PASS fresh pod oldUID=$before newUID=$after reads same PVC nonce=$nonce (not replicated durability)"
for url in http://fixture.proof-network-test.svc.cluster.local:8080/ http://192.168.254.254:8080/ http://198.51.100.1:8080/; do
 if "${K[@]}" -n proof-network-test exec deploy/denied-client -- wget -q -T 3 -O - "$url"; then echo "FAIL unexpected allowed $url" >&2; exit 1; fi
 echo "PASS request denied/timed out: $url (correlate Cilium policy evidence; timeout alone is not packet-drop proof)"
done
"${K[@]}" get ciliumclusterwidenetworkpolicy talos-proof-boundaries -o yaml
"${K[@]}" get nodes -o wide
"${K[@]}" get pods -A -o wide
"${K[@]}" get pvc -A
"${K[@]}" get pv
"${K[@]}" -n proof-gateway get gateway proof -o yaml
"${K[@]}" -n proof-network-test get httproute fixture -o yaml
"${K[@]}" -n proof-gateway get svc -o wide
# No metrics-server installed: process RSS/cgroup usage must come from Talos/provision worker.
"${K[@]}" -n kube-system exec ds/cilium -c cilium-agent -- cilium-dbg status --brief
