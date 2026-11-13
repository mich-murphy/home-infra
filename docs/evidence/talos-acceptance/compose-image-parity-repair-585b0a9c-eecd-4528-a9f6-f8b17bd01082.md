# Static Compose image-parity repair

## Scope and source

Implementation started from clean `feat/talos-live-proof` HEAD
`21d9464a88f5de957ea3523b23eb5ece999cad83`, after parent integration of main
`a2c549e7c5be06a3ef4971e49f98d41569a44766`.
Only the four assigned declarative manifests and this new evidence file changed.
Checked-out `docker/wallabag/compose.yml` and `docker/downloads/compose.yml`
are the image sources; neither Compose file was edited.

## CI root cause

Both failed runs were `pull_request` executions of `.github/workflows/talos-proof.yaml`.
Checkout has no explicit ref: CI tested PR #2005 synthetic merges, not feature-head trees.

| Run | Feature head | Actual checkout |
| --- | --- | --- |
| [43345591546](https://github.com/mich-murphy/home-infra/actions/runs/43345591546) | `cd003a97302b98d578a76938fc9433e0e5bdcfea` | `a1b648f5f07faea8952fbef7cee2662a4d1f42c2` |
| [43332534447](https://github.com/mich-murphy/home-infra/actions/runs/43332534447) | `164030dfcf83cb5ef09b2fd0fc8ba57f425be8cd` | `b65dba2873c4ae462367bcb50b97b00a115558be` |

Both merge commits have first parent `a2c549e7c5be06a3ef4971e49f98d41569a44766`.
Checkout logs and immutable GitHub Git-commit parents establish these identities;
nested PR metadata in historical run responses can reflect subsequently updated PR state.
Base commit `de55c07682875ec4dabc084ba675286f9a6c0542` updated Compose MariaDB;
`5c2ab7fd71bf4d650d01034afab8f8239cd305a5` updated Wallabag Redis;
`a2c549e7c5be06a3ef4971e49f98d41569a44766` updated SABnzbd.
The merges brought in new Compose pins but retained old proof pins.

`test_current_images_only` renders proof data Deployments and checks exact image
membership against checked-out Compose images. The feature head passed locally;
substituting the merge's Wallabag Compose text in memory reproduced its MariaDB
assertion failure. Redis also drifted; the later exact-service media test would
find SABnzbd drift. No registry resolution or running-cluster state is involved.
This repair preserves the existing current-Compose parity contract, without test
changes, head-only checkout, digest allowlists, or historical-evidence rewrites.

## Exact image substitutions

### Wallabag MariaDB — one occurrence

Path: `kubernetes/apps/data/wallabag/mariadb.yaml`

- Old: `mariadb:13.0.2@sha256:f4054da26e3a9dd6c8b5cc97363e544408b15c0fb369d7359c25dc04826eb6e1`
- New: `mariadb:13.0.2@sha256:54f493ea0d60b621a5bff84e5b20100f8b86b6efa6b79158e04756c5194a5e4d`

### Wallabag Redis — one occurrence

Path: `kubernetes/apps/data/wallabag/redis.yaml`

- Old: `redis:8.10.3-alpine@sha256:71885d8cc6e42f2bc0aa2eb853bfc4be200b5108a46ac50e117ae1df0531fb80`
- New: `redis:8.10.3-alpine@sha256:7958cfbb9d152f87dadfbc89f1b0b15938f0b81ff8982feb327476f4911935c3`

### SABnzbd — five occurrences

Paths: `kubernetes/apps/media/sabnzbd/resources.yaml` (two),
`kubernetes/apps/media/integration/sabnzbd.yaml` (three).

- Old: `ghcr.io/linuxserver/sabnzbd:5.1.3-ls280@sha256:693c208f697d0b411410edd92a98b52c8c754c01f5c078a975cbc892044260f5`
- New: `ghcr.io/linuxserver/sabnzbd:5.1.3-ls281@sha256:b356d0a9b22db584e9005364ec4e752dfc081ce501b7145e9a5c0bb38e4d1ba4`

## Focused offline validation

Executed in `/Users/mm/dev/home-infra-talos-proof`:

```sh
PYTHONDONTWRITEBYTECODE=1 KUBECONFIG=/dev/null python3 tests/talos-proof-data_test.py DataContract.test_current_images_only
PYTHONDONTWRITEBYTECODE=1 KUBECONFIG=/dev/null python3 tests/talos-proof-media_test.py Contract.test_every_current_compose_service_exact_digest
```

Results: each ran one test, both PASS.

The following Python render/validation procedure was executed with
`KUBECONFIG=/dev/null`; it only invokes local Kustomize rendering and the static
safety validator, not a Kubernetes API:

```python
import subprocess, yaml
for profile in ('data', 'media', 'media/integration'):
    rendered = subprocess.check_output(
        ['kubectl', 'kustomize', 'kubernetes/apps/' + profile], text=True)
    docs = list(yaml.safe_load_all(rendered))
    subprocess.run(['python3', 'tests/kubernetes-proof.py'],
                   input=rendered, text=True, check=True)
    print(profile, len(docs))
```

Results: data 120, media 188, media/integration 82 resources; all renders and
static safety checks PASS. `git diff --check` passed. The full static gate is
parent-owned and was not run by this worker; no schema/full-gate pass is claimed.

## Remaining old references and acceptance boundary

Repository search found no additional non-document references to the three exact
old digests after the seven substitutions. Existing historical references remain
unchanged in:

- `docs/evidence/talos-inventory/after-containers.json`
- `docs/evidence/talos-inventory/images.json`
- `docs/evidence/talos-inventory/before-containers.json`
- `docs/evidence/talos-inventory/compose-summary.json`
- `docs/evidence/talos-data/wallabag-image-queue-live-result.json`
- `docs/evidence/talos-data/wallabag-live-runtime.json`
- `docs/evidence/talos-media/live-download-transfers-observations.json`

Old live evidence remains tied to its recorded old images. New image pins have
only the offline validation described above, not renewed runtime/restore/capacity
acceptance. No runtime application, live API, SSH, credential access, apply,
reconciliation, or application activation was performed. Currently retained
stopped cluster objects may intentionally still contain old pins: this static
repair neither inspected nor reconciled them. Applications remain stopped under
parent-owned live coordination. Future source drift must continue to be tracked
and resolved under the current parity contract, not silently accepted.
