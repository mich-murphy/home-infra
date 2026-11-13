# Offline Flux-state classifier — implementation handoff

Source checkout HEAD: `0c0b8d97947cf6947f693678eb6fcf3f9cbfd042`.
Only new classifier, its new synthetic test suite, and this evidence leaf are owned.
No existing guards, admission rules, native CronJob/stopped-world barriers, or
other code/tests/docs were changed. No runtime/API/SSH, collection, app activation,
restart, resize, commit, or push occurred. Parent owns acceptance and full-gate scheduling.

## Interface and exact input contract

`evaluate(bundle) -> report` is pure and deterministic. The standard-library-only
CLI reads one saved JSON bundle from stdin, bounded to 16 MiB, and prints sanitized
JSON to stdout. No filenames, network, subprocesses, environment lookup, state
writes, or operational actions are used by the implementation.

```text
python3 scripts/talos-proof-flux-state.py < saved-bundle.json
```

The module docstring is the authoritative schema. Summary (all shown fields are
required and extra fields are rejected at these envelope/baseline levels):

```text
bundle = {
  schema_version: 1,
  baseline: {flux: [identity, ...], native: [native_identity, ...]},
  captures: {crds: capture, flux: [record, ...], native: [record, ...]}
}
identity = {gvr, kind, namespace, name, uid}
native_identity = identity + {execution_sha256}
record = {gvr, capture}
capture = {status: success|failed|missing, complete: boolean,
           scope: cluster|all-namespaces, list: captured-List-object|null}
```

GVR format is `group/version/plural`, with `core` denoting the empty API group.
CRDs require a complete cluster List; all resource Lists require all-namespaces
scope. Generic `v1/List` and matching typed Lists are accepted. CRD names/groups,
plural/kind, scope, and served versions determine resource-list coverage. One
selected served GVR per Flux CRD is required, not all equivalent served versions.
Missing/failed, partial, malformed, duplicate, or paginated lists never establish
complete coverage. Inventory is not inferred from the provided resource lists.

Native list GVRs are apps/v1 Deployments, StatefulSets, DaemonSets, ReplicaSets;
core/v1 ReplicationControllers and Pods; batch/v1 Jobs and CronJobs. These are
solely evidence dependencies for Flux absence, **not a replacement native safety
or platform evaluator**. Every native object must match an explicitly reviewed
non-Flux identity and execution digest, and every declared native object must be
observed. Unknown or changed machinery leaves conditional inertness unconfirmed.
The digest binds canonical JSON of:

```text
{"spec": object["spec"],
 "ownerReferences": object["metadata"].get("ownerReferences", [])}
```

Canonical serialization uses `json.dumps(sort_keys=True, separators=(',', ':'),
ensure_ascii=True)`, UTF-8, SHA-256. Digests are review bindings, not proof that the
baseline was reviewed correctly. Consumed native template/container, label, and
owner-reference shapes are checked independently of digest matches. Recognizable
Flux names, owner names, labels, and controller images block even a matching
baseline; recognition is not restricted to a namespace. The registry-port image
regression parses the final path component before its tag or digest.

Expected Flux identities bind GVR/kind/name/namespace/UID. Supported policies:

- GitRepository absent/false suspension: retained fetch intent, conditionally
  inert only with complete reviewed native absence evidence; not durably suspended.
- GitRepository true suspension: suspended fetch intent observation.
- Kustomization requires strict boolean true suspension; false/absent is a typed
  blocking observation, not an exception.
- Nonboolean suspension is malformed evidence. Unknown nonempty Flux kinds are
  incomplete policy coverage, not a universal suspension failure. A completely
  captured empty unsupported kind is observed empty without inspecting fields.

The evaluator accumulates available observations, blocked observations, and gaps.
`status` is `BLOCKED` if any observed policy violation exists; otherwise
`INCOMPLETE` if gaps exist; otherwise `OK`. `complete` independently means no gaps,
so a blocking observation cannot hide missing evidence. Exit codes are 1, 2, and
0 respectively. Reports contain fixed reason codes, fixed/indexed locations,
coverage metadata, and validated identity metadata only. They never echo raw specs,
URLs, secret-reference bodies, arbitrary error text, or exception representations.

Self-described capture success/scope/completeness and a declared baseline cannot
establish authenticity, freshness, or baseline provenance. Reports explicitly state
those limits, `offline_only: true`, and `runtime_authorization: false`. Even an
`OK` report is not fresh live acceptance or authorization. Native CronJob suspension,
native stopped-world, platform/node/PVC, capacity/admission, and live acceptance
remain outside scope and unchanged. There are no automatic operational instructions.

## Focused validation

Executed offline:

```text
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-flux-state_test.py
21 tests, OK (0.024 seconds on the recorded focused run)
git diff --check
```

Synthetic tests are self-contained: no private-capture dependency or conditional
skip. They cover the missing-field GitRepository regression, Kustomization true/
false/absent, cross-namespace Flux controllers/Pods including terminal/terminating,
matching-baseline registry-port images, unbound or changed native objects, malformed
consumed native shapes, missing later Kustomization, unsupported empty/nonempty
kinds, missing/failed/partial/paginated/duplicate/malformed captures and inventory,
identity drift, strict booleans, simultaneous findings/gaps, output redaction,
bounded stdin and parse failures, determinism/input immutability, and patched
file/subprocess/socket entry points during pure evaluation.

No full gate was run; parent will schedule it.

## Actual historical replay (offline, originals preserved)

Read only the six explicitly permitted files under the private diagnostic directory
`guarded-platform-recovery-201099d8-0301-4c6b-8b14-512b51cf5d05`. The historical
verifier was read/hashed, **not executed**. An in-memory bundle used the actual
CRD inventory, actual GitRepository List, actual Pod List, and native objects from
the actual combined-controller List. Its partitioned controller Lists were marked
**partial**, because a combined List does not establish separate per-GVR success.
No native baseline was invented from those observations. The known reviewed
GitRepository identity was declared; no Kustomization or later Flux list was filled
in as empty. No replay fixture or private result file was written.

Actual replay result:

```text
status: INCOMPLETE
complete: false
blocked_count: 0
observation_codes: [SUSPEND_FIELD_ABSENT]
gap_codes: [FETCH_INERTNESS_UNCONFIRMED, LIST_MISSING, LIST_PARTIAL, NATIVE_UNBOUND]
```

Thus the historical missing-field finding is preserved, not reclassified as a
universal suspension hazard. The new classifier itself does not independently
establish historical controller absence: absent reviewed native bindings and
per-GVR coverage remain gaps. The parent review's bounded historical conclusions
and the original administrative-stop evidence remain unchanged. Current
Kustomization/later Flux state remains UNOBSERVED.

SHA-256 before and after replay matched for every permitted original:

| Original basename | SHA-256 |
| --- | --- |
| exact-followup.py | `32fc9184147b6d935752522f24b3095881a935b18e879d33043d9ba25b18947f` |
| exact-flux-gitrepositories.source.toolkit.fluxcd.io.stdout | `c31296f83249a576a1bd02f8ef74cb4aceeaa0c470c20f6e9bca28d6da28c5ff` |
| exact-controllers.stdout | `f9464329c4f183a0d49c902a261599aeb7ce561e7f6f106cfb1aa7b72a10aa66` |
| exact-pods.stdout | `8a7636516cf8fc8930c9cc9035d696d25bb3527ee12182be3347942eb0af05c9` |
| exact-crds.stdout | `961e4c939bb838dd2ebed58784f87f2fff44f27d78021d5245db06f5244fcad1` |
| exact-verification-failure.json | `5607c7064288e3a60691078affc6b40af26d9325c8a68243ce58da03895418df` |

## Release

Implementation is uncommitted and released to parent review. No runtime ownership
or authority is claimed. Pre-existing unrelated checkout changes were left alone.
