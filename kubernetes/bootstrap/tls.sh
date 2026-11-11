#!/usr/bin/env bash
set -euo pipefail
: "${KUBECONFIG:?}" "${PROOF_CONTEXT:?}"
umask 077
D=$(mktemp -d);trap 'rm -rf "$D"' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 7 -keyout "$D/key" -out "$D/cert" -subj '/CN=*.proof.invalid' -addext 'subjectAltName=DNS:*.proof.invalid' >/dev/null 2>&1
kubectl --context "$PROOF_CONTEXT" -n proof-gateway create secret tls proof-tls --key="$D/key" --cert="$D/cert" --dry-run=client -o yaml | kubectl --context "$PROOF_CONTEXT" apply -f -
echo 'Synthetic self-signed proof TLS secret applied; use explicit --cacert certificate for verification.'
