# Isolated Talos proof: operator guide

> **Not approved for migration.** This is a separate, resource-bounded proof profile.
> Docker remains authoritative and unchanged. A passing static CI job is not a
> functional, recovery, capacity or production-readiness verdict. Current live
> acceptance and outstanding corrections are in [the delivery record](talos-proof-delivery.md).

## Bounded live evidence so far

- **Platform:** Ready control plane, dedicated XFS/PVC persistence, real NodePort
  trusted TLS and correlated Cilium policy drops; guard crash/watchdog stop and
  recovery tested. Actual node TCP rejection now has same-endpoint live controls
  and correlated adjacent predicate/REJECT counters with unchanged policy/cleanup.
  This is not full-five-tuple tracing. Host reboot and DNS/IPv6/bypass coverage
  remain unproved.
- **Data:** CouchDB document persistence/recovery, Miniflux feed/read-state recovery,
  actual Pocket-ID browser WebAuthn/signed OIDC and recovery, and Wallabag HTTP
  OAuth/article extraction/CRUD/recovery. Wallabag's exact synthetic fixture needs
  a documented narrow SSRF adapter; this is not production configuration parity.
  Expanded CouchDB tenant/view/replication/security recovery and Miniflux
  bookmark/preferences recovery passed. Pocket-ID retained-passkey/protocol negatives
  passed across replacement/freshPVC; Wallabag actual image/native Redis import passed
  (fresh-process reconnect; imagePVC retained). Parent independently checked earlier
  archive hashes and distinct live PVC/PV/XFS paths, including the newest Pocket-ID
  and Wallabag captures. This is not another functional replay; restart/resource
  caveats remain.
- **Operations:** observations/loopback alerts and off-node file restore passed;
  private etcd snapshot captured, **not restored**. After a genuine fresh capacity
  improvement, Flux reconciliation/drift repair/path rollback/negative RBAC passed.
  The earlier memory refusal and unexplained first apply failure remain recorded.
  Snapshot hash/embedded checksum independently match; the [same-VM recovery
  proposal](talos-proof-etcd-recovery-plan.md) still needs an explicit exception
  to the separate-target policy. No reset/reboot authority exists.
- **Media:** Pinchflat profile recovery and Audiobookshelf fixture streaming/state
  recovery passed. qBit/BEP3 and SAB/NNTP now have actual32,044-byte local transfers,
  exact output hashes, fixture-off restart and distinct-PVC functional recovery.
  Native qBit browser login/authenticated hostile-form denial also passed, but its
  cookie lacked Secure behind TLS termination. Later Plex scan/bytes/range/watched
  CRUD passed, but native Origin/Referer401 blocks browser playback. Jellyfin leaked
  exact video bytes to an anonymous client; Pinchflat RPC hit OOM before provider
  proof. A later704MiB trial verified bundled lightweight transport identity but
  returned no structured RPC result; provider work was not reached. Main384MiB
  peak/max2028 and cleanup STOP are preserved. Source-backed MFA fixes passed
  workstation tests only; no retry/grant exists. These are blockers, not acceptance.
- **Heavy data:** CODE established real WOPI read/lock and token/lock negatives,
  but eight attempts (sevenTXT, one nativeODT) did not reach typing/save/reopen;
  actualODT loaded with edit permission but a session warning blocked automation.
  No Office editing acceptance. A native cron side-effect runner and stopped/read-only
  initialization path are prepared, not executed; Nextcloud PVCs are still absent.
  Actual ML inference and full Nextcloud/Immich integration remain unproved.

See the [all36-service readiness matrix](talos-proof-readiness.md), service-specific
evidence and [current delivery record](talos-proof-delivery.md) for exact scope,
limitations and active ownership. This is not a full concurrent
replica, a production-data migration rehearsal or approval to retire Docker.

## Layout and ownership

| Path | Purpose |
|---|---|
| `infrastructure/proxmox-proof/` | Guarded creation/start of proof VM120 only; isolated networking and host resource protection |
| `talos/` | Version-pinned, secret-free machine patches and private config generation |
| `kubernetes/platform/` | Cilium, native Gateway API, local storage and isolation policies |
| `kubernetes/bootstrap/` | Checksum-locked artifacts, explicit-target install, TLS and platform experiments |
| `kubernetes/apps/data/` | Nextcloud/Collabora, Immich/ML, Miniflux, Wallabag, CouchDB, Pocket-ID |
| `kubernetes/apps/media/` | Players, library managers, downloaders and suspended integration jobs |
| `kubernetes/operations/` | Narrow GitOps fixture, observability/alert and clean-volume recovery experiments |
| `scripts/*talos-proof*`, `tests/*proof*` | Reproducible static and explicitly authorized live checks |
| `docs/evidence/talos-*/` | Sanitized evidence, including negative results and limitations |

Production Terraform and Ansible **do not manage this proof**. Never run the old
Kubernetes branch's cutover, `enable_talos` switch, router role or Docker rollout
as part of this work. Those can stop/reconfigure production services.

Read [the inventory](talos-proof-inventory.md) before judging service coverage:
36 live containers map to 32 app workloads and four infrastructure capabilities.
Replacing Traefik, Portainer, Beszel and the socket proxy means proving ingress,
declarative reconciliation, monitoring and management boundaries, not attaching a
Docker socket to Kubernetes.

## Why this profile is deliberately small

The 32-GiB host already runs two 10-GiB guests. Their allocations, production GPU,
NAS exports, DNS and router rules are unchanged. Source Docker containers alone
measured 3.525GiB idle, before Talos/Kubernetes or peak workload demand. The proof
therefore started with2560MiB and tests **one bounded dependency group at a time**.
A later fresh admission safely permitted3072MiB for VM120 only; an earlier attempt
was refused and remains recorded. Talos MemAvailable and kubelet available memory
have differed substantially due to active-file-cache accounting. Preserve each
gate's metric and record both; do not treat optimistic available memory as proof
of representative capacity. No other guest allocation or host tuning changed.
All application Deployments default to zero replicas; CronJobs default suspended.
Applying all app declarations must not start the whole stack.

The dedicated 64-GiB disk is XFS local storage with Retain claims. It protects
against accidental automatic PVC cleanup, **not** node/disk loss. Mayastor's engine
memory/hugepage requirements do not fit, and one node cannot prove replication.
Off-node backup and clean-PVC restore are separate gates. A host ZFS mirror is not
application-aware backup, HA, or tested disaster recovery.

QEMU user-mode networking avoids changing host forwarding or production VLANs.
The node and Gateway are available only through SSH loopback forwards. This is a
safe experimental boundary, **not production VLAN/L2/real-client network parity**.
The host filter is scoped to proof QEMU sockets; Cilium adds workload boundaries.
Both layers need positive-control and negative-test evidence.

## Static validation (no host or cluster changes)

```sh
nix shell .#kubectl .#kubeconform .#shellcheck .#kubernetes-proof-tools \
  --command bash scripts/check-talos-proof.sh
```

The gate renders both app groups and the separate shared media integration profile,
requires stopped/suspended defaults, explicit
proof namespaces, immutable images, resource budgets, probes, token suppression,
restricted mounts/exposure and default isolation. It validates standard resources
and checksum-locked Cilium/Gateway schemas with **zero missing-schema skips** and
runs regression tests for unsafe mutations. CRD CEL/controller behavior still
requires live API admission and datapath tests.

Talos validation must use the matching downloaded client, not an older Nix client:

```sh
export STATE
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
bash infrastructure/proxmox-proof/bootstrap-tools.sh
bash talos/generate.sh
bash infrastructure/proxmox-proof/validate.sh
```

This generates temporary identity material outside the checkout. Never overwrite
an existing live identity to refresh a validation fixture.

## Live workflow and guardrails

1. Read [platform provisioning](talos-proof-platform.md) and inspect measured host
   available memory, swap deltas, PSI and running guests. Create/start **VM120 only**
   through the guarded wrapper, not unrestricted `qm start`. The proof is not
   automatically started after a Proxmox reboot. Verify the proof-only exclusion
   from the existing all-guests backup job so experimental data does not silently
   enter production NAS backups; see the explicit membership exception in the
   platform runbook. Existing guests' backup settings remain unchanged.
2. Verify authenticated Talos, etcd, Kubernetes `/readyz`, node identity and the
   **dedicated** `/var/mnt/proof` mount. Do not infer Kubernetes health from healthy
   Talos services or a running VM. Preserve failed experiments in the evidence.
3. Follow [bootstrap](../kubernetes/bootstrap/README.md). Set an explicit private
   kubeconfig, context and expected API URL. Install only on the verified proof
   node. Validate storage, DNS, deny rules and actual NodePort HTTP/trusted TLS.
   Discover the assigned Gateway NodePorts; do not assume requested hostforward
   ports match them. Service port-forward bypasses the ingress datapath.
4. Grant one measured resource lease. Use the [data](talos-proof-data.md) or
   [media](talos-proof-media.md) lifecycle. Generate fresh secrets privately, start
   only the selected group, perform functional writes/reads/negative auth tests,
   capture state identity, restart, and verify preserved state **before rewriting
   the fixture**. Scale the group down and wait for pod deletion before the next.
5. Run [operations](talos-proof-operations.md): real resource observations and alert
   delivery, off-node archive/clean-PVC restore, then bounded GitOps drift repair
   and rollback using a pinned public commit. Capture an etcd snapshot privately;
   obtaining a snapshot does not prove recovery.
6. Recheck source container IDs/start times/restarts and host resources. Attribute
   any independently automated source replacement from evidence; don't call a
   changed source unchanged. Leave only explicitly documented proof workloads on.

Private live state is under `$HOME/.local/state/home-infra/talos-proof` on the
operator workstation. Never commit kubeconfig, Talos machine config, CA keys,
secrets, database dumps, tokens, raw app logs or archives. The expected management
API is `https://127.0.0.1:64120`; obtaining an unrelated context with the same name
must not authorize mutation. Production credentials and production data are not
required for synthetic functional proofs.

## Evidence and acceptance

For each result record UTC time, source commit plus dirty-file identity if any,
exact command, resource/image/PVC identities, fixture checksum, observed outcome
and limitations. Explicitly distinguish:

- **Static pass:** declarations and safety contracts validate.
- **Startup pass:** workload becomes ready with no unexplained restarts.
- **Functional pass:** intended synthetic behavior produces checked output.
- **Integration pass:** dependency/ingress/auth path works across real boundaries.
- **Recovery pass:** preserved state and independently restored state match.
- **Capacity pass:** representative concurrent load and peaks fit safely.

A denied request to an unreachable address is not isolation proof. An empty
helper configuration is not a useful successful job. An HTTP health response is
not passkey authentication, WOPI editing, ML inference, media playback or torrent
transfer. One successful fixture is not historical production-data restore.

Before any future migration, separately pass full concurrency/soak, native VLAN
and client policy, production-data backup/restore rehearsal, OIDC/passkey
continuity, storage topology/hardlinks, GPU/transcoding capacity, monitoring and
notifications, upgrade/rollback, certificate renewal and off-node disaster
recovery. Single-node deployment must explicitly accept its lack of availability
when the node is down. **No DNS cutover or source decommission is authorized by
these proof scripts.**
