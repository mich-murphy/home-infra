# Media static validation receipt

These checks ran locally in `/Users/mm/dev/home-infra-talos-proof`. **No cluster workloads deployed, no live resource lease used, no functional/runtime/persistence/recovery/isolation pass claimed.**

Commands and observed results:

```text
python3 tests/talos-proof-media_test.py
Ran 5 tests ... OK

kubectl kustomize kubernetes/apps/media | python3 tests/kubernetes-proof.py
Proof application safety checks passed (static checks, not runtime acceptance).

bash -n scripts/talos-proof-media-batch.sh
exit 0

python3 -m py_compile scripts/talos-proof-media-bootstrap.py scripts/talos-proof-media-fixture.py tests/talos-proof-media-functional.py
exit 0
```

Offline tests cover all 16 current Compose exact digest references, namespace/default-deny/dependency safety, bounded suspended real helper invocation, private secret generation/refusal to silently rotate, deterministic 32,044-byte generated WAV. Private temporary secrets from unit tests were deleted automatically and were neither printed nor committed.

Pending: coordinator review of functional tests, explicit kubeconfig + lease, real API compatibility checks, seven currently executable service functional test paths, remaining service-specific functional test implementation, proof storage topology integration, helper nonempty dry-runs, resource measurements, restart and clean-PVC restore. See `docs/talos-proof-media.md` for the full honest matrix.

Gateway follow-up: all 13 UI HTTPRoutes attach to proof-gateway/proof on reserved `<service>.proof.invalid` hosts, with proof-gateway namespace and Cilium ingress-identity port-specific policies. Re-rendered safety and five offline contract tests pass. Live Gateway/Cilium identity enforcement remains untested and subject to parent review.

Safety/TLS follow-up: seven safety tests and four real local TLS tests pass, alongside the five existing contract tests (16 methods total). Wrong production endpoint, HTTP API endpoint, insecure API TLS, wrong context/node name/hostname/UID, multi-node targets, credential plugin, expired/mismatched leases, concurrent data/media/unknown proof groups and stale/insufficient memory are rejected offline. Trusted Gateway client tests use ephemeral certificates/server only; wrong CA and certificate hostname fail. No real cluster command or live deployment was performed for these tests. Python compilation and rendered parent safety validation also pass.
