# Bootstrap target-override hardening — offline evidence

## Scope and target

Source-only safety hardening; **no live deployment or cluster mutation** was run.
No host/Docker configuration was changed. Tests create temporary synthetic files
and mock executables; no private kubeconfig or credentials were read or printed.
Existing live platform evidence remains separate in `live-summary.md`; this change
does not re-verify or supersede it.

The unchanged public `kubernetes/bootstrap/proof-target.json` pins:

- API: `https://127.0.0.1:64120`
- Sole node: `talos-proof`
- Node UID: `4845bfd5-3bdb-453d-8503-83b43edb7a1e`
- InternalIP: `172.31.250.10`

## Findings confirmed from repository source

1. **Kubectl server shorthand bypass.** The prior guard rejected `--server` but
   not `-s URL`, `-sURL`, or Cobra boolean clusters containing that shorthand.
   After a successful config/node check it could execute a command with a new
   server override. A temporary copy of the prior guard was exercised against
   synthetic mock kubectl: `apply -f synthetic.yaml` with `-s URL` and
   `-sURL`, and `exec pod -itsURL -- true`, each returned zero and reached
   the final mock command. No real
   kubectl/API call was made. This is a confirmed validation/execution gap, not
   evidence that a live wrong-target mutation occurred.
2. **Helm transport inheritance.** The installer previously supplied only
   `--kube-context` after the guard check. It neither rejected `HELM_KUBE*`
   overrides nor pinned Helm's API endpoint/kubeconfig/TLS verification explicitly.
   Helm's independent transport configuration could therefore differ from the
   kubectl precheck. This finding was established by source audit; no real Helm
   connection or wrong-target reproduction was attempted.
3. The prior kubeconfig validator also accepted `proxy-url` and `tls-server-name`.
   Both are now rejected rather than allowing unchecked transport overrides.

## Hardened behavior

- Validate kubectl arguments **before any subprocess**. Refuse endpoint, cluster,
  kubeconfig, user, TLS, credential, impersonation, proxy and preference overrides.
  Reject long `--flag value`/`--flag=value` and underscore-normalized variants.
  Reject `-s`, `-sURL`, `-s=URL`, and server shorthand within boolean clusters.
- Handle known value-taking short flags as values (`-nnamespace`, `-fpath`, etc.),
  not as clusters. Unknown short options fail closed. Continue allowing the exact
  required context; reject a changed or missing context value.
- Stop at the kubectl `--` separator. An in-container command such as
  `exec -it pod -- curl -s --server=...` is passed through unchanged; these are
  not kubectl target flags.
- Explicitly supply kubeconfig/context/pinned endpoint for kubectl node checks
  and final execution. Inspect the configured endpoint **without** injecting a
  server override into `config view`, so a wrong config cannot be hidden by the
  pin. Require one kubeconfig file, not a merged path-list.
- Reject the presence (even empty) of all `HELM_KUBE*` variables,
  `KUBERNETES_MASTER`, and upper/lowercase `HTTP_PROXY`, `HTTPS_PROXY`,
  `ALL_PROXY`. The first installer guard runs before downloads or mutations.
  `NO_PROXY` alone cannot introduce a proxy and need not be rejected.
- Disable kubectl preference-file defaults/aliases with `KUBECTL_KUBERC=false`;
  reject other supplied values and `--kuberc` overrides.
- Immediately before Helm, recheck identity; pass explicit `--kubeconfig`,
  `--kube-context`, `--kube-apiserver` and
  `--kube-insecure-skip-tls-verify=false`. CA and credentials come from the
  dedicated checked kubeconfig, not inherited Helm transport/auth overrides.
- Guard failures use a generic diagnostic without echoing arguments, config
  contents, credential values, or subprocess exception command lines.

## Offline validation

Executed in `/Users/mm/dev/home-infra-talos-proof`:

```text
python3 kubernetes/bootstrap/test_safety.py
Ran 11 tests — OK
shellcheck kubernetes/bootstrap/*.sh
PASS (exit 0)
for script in kubernetes/bootstrap/*.sh; do bash -n "$script" || exit; done
PASS (exit 0)
git diff --check
PASS (exit 0)
```

The unit suite includes multiple subcases per test. Mock-CLI negative cases
exercise flag overrides both before and after the kubectl command and assert
**zero CLI invocations**, hence no mutator invocation. Environment negative cases
run the actual installer against synthetic mock tools and assert no kubectl or
Helm invocation. Config transport-negative cases permit only the read precheck,
never the mutator. A positive mocked installer completes and verifies the actual
Helm argv pins; a positive mock exec verifies container arguments after `--` are
preserved. Existing endpoint, UID/IP, single-node, TLS and mount fallback tests
also pass. Downloads are stubbed; no network access is needed.

## Limits and remaining trust

These tests validate wrapper behavior and argument construction, not a real
kubectl/Cobra or Helm SDK implementation. They do not exercise real TLS, live
identity, live mutations, storage, network policies, or deployment health. No
new live verification is needed to establish the source regression fix.

This guard prevents accidental transport/configuration overrides; it is not a
sandbox against a malicious local operator. It trusts executables on PATH, the
private kubeconfig (including its CA, credentials and credential plugins), and
local configuration integrity between check and execution. It does not defeat
concurrent kubeconfig replacement, executable replacement, SSH-forward changes,
or direct tool invocation outside the wrapper. Existing live evidence and human
authorization requirements remain unchanged. Future kubectl shorthand additions
require review; unknown forms are intentionally refused rather than guessed.
