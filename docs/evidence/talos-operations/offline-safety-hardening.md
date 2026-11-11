# Operations offline safety checkpoint

Status: **OFFLINE ONLY; no live operations lease and no cluster mutation.** Supersedes the old `vm120` environment-marker gate in the initial operations checkpoint. This is not a monitoring, GitOps reconciliation, backup restore, or etcd recovery pass.

## Implemented

- Owner-only 0600 coordinator JSON receipt inside the private proof state; owner-only0700 directories; reject original path/ancestor symlinks before resolution.
- Every Kubernetes invocation rechecks exact `https://127.0.0.1:64120`, verified TLS, consistent context/cluster/user mapping, no proxy or credential subprocess/provider, single `talos-proof` node/hostname, InternalIP `172.31.250.10`, fixed UID `4845bfd5-3bdb-453d-8503-83b43edb7a1e`. Actual calls pin config/context/server.
- Receipt binds `operations` or `operations-flux`, endpoint/context/fixed UID, expiry and fresh guest available-memory measurement. Copied private production configuration, including consistently wrong receipt context/server, cannot authorize mutation.
- Snapshot uses only the fixed private Talos v1.14.5 client and fixed endpoint `127.0.0.1:50120`/node `172.31.250.10`; no caller target/PATH selection. Snapshot metadata explicitly says restore untested.
- Recovery rejects an existing namespace, distinct-PVC UID/PV checks, exact claim binding and Retain verification, nonempty-data rejection, source noclobber, exclusive-create workstation archive, keep-old-files extraction, source pod removed before restore, pod-only finally cleanup. Both PVCs/PVs remain for diagnosis; no data wipe or storage deletion.
- Guarded Flux run/cleanup replaces ambient manual mutation instructions. Render remains nonmutating; run consumes only generated checksum-locked release YAML, requires actual kubelet memory reserve, performs fixture drift/rollback/negative-RBAC checks and always attempts gated controller cleanup. Cleanup never removes CRDs, namespaces or storage.

## Offline verification

```text
python3 tests/talos-proof-operations_test.py
Ran 14 tests
OK

python3 -m py_compile scripts/talos-proof-operations.py scripts/talos-proof-operations-flux.py tests/talos-proof-operations_test.py
PASS

kubectl kustomize kubernetes/operations/recovery > /dev/null
PASS (local render only)

git diff --check -- <explicit operations-owned paths>
PASS
```

Tests include endpoint/TLS/context/user/node/count/IP/UID mutants, consistent wrong target receipt, stale/expired/wrong-group receipt, file mode and symlink ancestor rejection, denied exec/mutation/cleanup, nonempty recovery, duplicate claim UID/PV, non-Retain PV rejection, archive no-overwrite, source deletion ordering, partial-apply pod cleanup, snapshot target/version/config/no-overwrite and Flux denied lease/partial cleanup.

## Remaining live gates

Actual kubelet measurements and HTTP alert receipts, off-node archive creation and clean-PVC checksum restore, controller startup/RBAC/reconciliation/drift/rollback, resource before/during/after samples and eventual separate-outage-approved etcd recovery remain **NOT EXECUTED**. An etcd snapshot is not a restore pass. Private archives/snapshots/configs must never enter Git. Expired/stale receipt or changed identity blocks cleanup too; coordinator must refresh an approved receipt rather than bypassing target validation. The independent host guard remains necessary during such a stop.
