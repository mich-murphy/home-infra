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

Integration/API follow-up: six offline integration test methods pass, bringing the total to 22 (6 integration + 5 contract + 7 safety + 4 TLS). Both isolated and explicit shared-data integration renders pass the parent validator. qbitwebui, Audiobookshelf and Pinchflat exact-version functional procedures and read-before-write persistence modes are implemented but NOT RUN LIVE. Nonempty Recyclarr local-resource preview execution/checking is implemented but NOT RUN LIVE. No lease or live cluster mutation occurred.

Local-unclaimed/contract/recovery follow-up:30 offline test methods pass (6 contract +8 safety +4 GatewayTLS +6 integration +6 fixture tests). Real ephemeral-local TMDb CONNECT/TLS returns synthetic contract data and rejects a different CONNECT host; recovery tar mutants reject traversal/unsafe links/devices; adapter accepts only fresh proof key/Basic credentials. Both renders pass parent validator. Local Mac ffmpeg generated a14,790-byte MPEG4/AAC160x90 fixture with SHA256 e2caeabdadb83d31b59e1049699f9538cc8ff04e61a3e6b389cbadf20697339b; ffprobe duration2.128027s. No live app/restore/helper pass is claimed.


2026-11-11T14:28Z reassigned-worker offline first-batch preparation: all33 test methods pass (`for t in tests/talos-proof-media*_test.py; do python3 "$t" || exit; done`):6 fixture +6 integration +3 observation/durable-qbit +8 safety +4 local TLS +6 contract. Shell syntax and explicit-path diff whitespace checks pass. New qBittorrent verification reads retained preferences before any settings write and rejects lost state. Observation tests preserve an older OOMKilled/restartCount3 pod alongside a newer restartCount0 pod, redact termination messages, retain cgroup counters, and create two immutable records. Lifecycle now captures before restart/stop/failed-rollout deactivation; stopped-volume snapshot captures before stopping. No cluster command, live lease, bootstrap of actual proof state, or application acceptance occurred. Ready to request first Pinchflat lease from parent; operations still owns the live window. Tautulli/Seerr/Kometa and protocol transfer acceptance remain pending.
