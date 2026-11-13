# Nextcloud initialization review: grant withheld

Reviewed source: `237ea686`; read-only reviewer `5526425f-cd5d-4f7`.
Parent independently inspected the incomplete envelope normalizer. No runtime,
credential, host or grant access was performed by the reviewer. These findings
concern the reviewed commit; subsequent repairs require separate acceptance.

## Blocking findings

1. **API-default compatibility:** full PodSpec comparison normalizes quantities
   but omits probe defaults, HTTP scheme, ConfigMap defaultMode and downward-API
   fieldRef apiVersion. Approved provisioner/backend API objects can be rejected.
   Fix exact known defaults, retaining unknown/security/resource drift rejection.
2. **Create authority:** missing-object names are allowed, but intended document
   hashes are not receipt-bound; no independent pre-create replicas0/suspend=true
   assertions. Current declarations are stopped; this is a conditional declaration
   drift gap, not an observed unauthorized activation.
3. **Serialization:** initializer/supervisor locking does not cover the legacy
   data CLI check-to-mutation path. Pending detection alone is not concurrent
   serialization. No actual competing live writer was observed.
4. **Retirement:** auxiliary provisioner listing failure can prevent capture and
   UID-bound retirement of the owned binding Job. Retain the gap but still try
   owned-helper retirement when its API is reachable.
5. **Native cleanup identity:** full supervisor stop lacks namespace UID binding
   and scales backend names without an atomic object-identity precondition. A
   narrow cleanup identity gate must not require a passing activation envelope.
6. **Private errors:** real life.kube failure discards captured stdout/stderr;
   mocked CalledProcessError tests do not exercise that real path. Sensitive
   diagnostic retention must be implemented without public message/argv leaks.

Relevant paths: `scripts/talos-proof-nextcloud-initialize.py`,
`talos-proof-nextcloud-cron-supervisor.py`, `talos-proof-data.py`, their tests,
and `docs/talos-proof-nextcloud-cron-plan.md`.

## Preserved bounded positives and limits

Create-only/no Secret creation; read-only pinned BusyBox binding helper; actual
64+3x32+192=352MiB envelope with conservative832MiB dual-min admission; normal
capture-before-UID-delete; explicit automatic-provisioner forensic gaps. These
are source-level properties, not storage, runtime, initialization or cron proof.

Parent still observed zero Nextcloud PVCs. **No initialization or native-cron
grant issued.** A reviewed initialization receipt and separate new postbinding
UID receipt remain necessary. Repair ownership transferred exclusively to
`179dd28c-5cf7-4e9`, OFFLINE only. Original WOPI failures and all private evidence
remain untouched.
