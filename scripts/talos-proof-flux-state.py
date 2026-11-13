#!/usr/bin/env python3
"""Pure OFFLINE Flux-state classification; no live authority or collection.

stdin CLI: one saved JSON bundle, at most MAX_INPUT_BYTES; stdout: sanitized JSON.
Exit 0 = OK, 1 = BLOCKED, 2 = INCOMPLETE (including invalid JSON).

Exact schema (all fields required; no extra fields):
  {"schema_version": 1,
   "baseline": {"flux": [identity, ...], "native": [native_identity, ...]},
   "captures": {"crds": capture, "flux": [record, ...], "native": [record, ...]}}
  identity = {"gvr": "group/version/plural", "kind": "Kind",
              "namespace": "dns-label", "name": "dns-subdomain", "uid": "uuid"}
  native_identity = identity + {"execution_sha256": "64 lowercase hex chars"}
  record = {"gvr": "group/version/plural", "capture": capture}
  capture = {"status": "success"|"failed"|"missing", "complete": bool,
             "scope": "cluster"|"all-namespaces", "list": object|null}

Use 'core' in GVR strings for the empty API group. CRDs must be a complete
cluster-scoped apiextensions.k8s.io/v1 CRD List. Every Flux CRD (group ending
'.toolkit.fluxcd.io') needs one complete all-namespaces List at a served version;
all NATIVE_GVRS below also need complete all-namespaces Lists. Generic v1 List
and correctly typed lists are supported. Pagination is not assembled.

Native baseline entries are explicitly reviewed NON-FLUX exceptions, not proof
from a boolean. execution_sha256 binds canonical JSON of
  {"spec": object["spec"], "ownerReferences": metadata.get("ownerReferences", [])}
using json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=True), UTF-8.
Every captured native object must match its baseline identity and digest; every
baseline native object must be observed. Recognizable Flux machinery is blocked
even if included in the baseline. Digests and self-described coverage cannot
establish authenticity, freshness, or baseline provenance. A malicious/reviewed-
incorrect baseline cannot be disproved from saved JSON alone.

Only expected GitRepository and Kustomization identities have supported policy.
GitRepository absent/false suspension is conditionally inert only with complete,
baseline-bound native captures; never durably suspended. Kustomization must have
strict boolean true suspension. Unknown nonempty kinds are INCOMPLETE, not a
universal suspension failure. Native captures are solely an evidence dependency
for Flux absence: this does NOT evaluate native CronJob suspension, platform,
node, PVC, capacity, stopped-world, or other runtime/admission gates.

Output is metadata only: fixed codes, fixed/indexed locations, validated resource
identities and coverage. No bodies, URLs, exception text, or operational advice.
"""
import hashlib
import json
import re
import sys

MAX_INPUT_BYTES = 16 * 1024 * 1024
NATIVE_GVRS = {
    'apps/v1/deployments': 'Deployment',
    'apps/v1/statefulsets': 'StatefulSet',
    'apps/v1/daemonsets': 'DaemonSet',
    'apps/v1/replicasets': 'ReplicaSet',
    'core/v1/replicationcontrollers': 'ReplicationController',
    'batch/v1/jobs': 'Job',
    'batch/v1/cronjobs': 'CronJob',
    'core/v1/pods': 'Pod',
}
SUPPORTED = {
    ('source.toolkit.fluxcd.io', 'gitrepositories'): 'GitRepository',
    ('kustomize.toolkit.fluxcd.io', 'kustomizations'): 'Kustomization',
}
FLUX_NAMES = ('source-controller', 'kustomize-controller', 'helm-controller',
              'notification-controller', 'image-reflector-controller',
              'image-automation-controller', 'source-watcher')
IDENTITY_KEYS = {'gvr', 'kind', 'namespace', 'name', 'uid'}
LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')
UID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
KIND = re.compile(r'[A-Z][A-Za-z0-9]{0,62}\Z')
VERSION = re.compile(r'v[0-9]+(?:(?:alpha|beta)[0-9]+)?\Z')


def _dns(value):
    return (isinstance(value, str) and len(value) <= 253
            and all(LABEL.fullmatch(part) for part in value.split('.')))


def _gvr(value):
    if not isinstance(value, str):
        return None
    parts = value.split('/')
    if (len(parts) == 3 and _dns(parts[0]) and VERSION.fullmatch(parts[1])
            and LABEL.fullmatch(parts[2])):
        return tuple(parts)
    return None


def _identity(value):
    if not isinstance(value, dict):
        return None
    if not IDENTITY_KEYS <= value.keys():
        return None
    if not (_gvr(value['gvr']) and isinstance(value['kind'], str)
            and KIND.fullmatch(value['kind']) and isinstance(value['namespace'], str)
            and LABEL.fullmatch(value['namespace']) and _dns(value['name'])
            and isinstance(value['uid'], str) and UID.fullmatch(value['uid'])):
        return None
    return {key: value[key] for key in sorted(IDENTITY_KEYS)}


def _key(identity):
    return tuple(identity[k] for k in ('gvr', 'namespace', 'name'))


def _execution_digest(obj):
    payload = {'spec': obj['spec'],
               'ownerReferences': obj['metadata'].get('ownerReferences', [])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True).encode()).hexdigest()


def _pod_spec(obj):
    spec = obj.get('spec')
    path = ('jobTemplate', 'spec', 'template', 'spec') if obj['kind'] == 'CronJob' else (
        () if obj['kind'] == 'Pod' else ('template', 'spec'))
    for field in path:
        spec = spec.get(field) if isinstance(spec, dict) else None
    return spec if isinstance(spec, dict) else None


def _native_shape(obj):
    """Validate only shapes consumed for recognition and reviewed binding."""
    meta = obj['metadata']
    refs = meta.get('ownerReferences', [])
    if not isinstance(refs, list):
        return False
    owner_uids = set()
    for ref in refs:
        if (not isinstance(ref, dict)
                or not isinstance(ref.get('kind'), str) or not KIND.fullmatch(ref['kind'])
                or not _dns(ref.get('name'))
                or not isinstance(ref.get('uid'), str) or not UID.fullmatch(ref['uid'])
                or not isinstance(ref.get('apiVersion'), str) or not ref['apiVersion']
                or any(k in ref and type(ref[k]) is not bool
                       for k in ('controller', 'blockOwnerDeletion'))):
            return False
        if ref['uid'] in owner_uids:
            return False
        owner_uids.add(ref['uid'])
    if sum(ref.get('controller') is True for ref in refs) > 1:
        return False
    labels = meta.get('labels', {})
    if not isinstance(labels, dict) or any(not isinstance(v, str) for v in labels.values()):
        return False
    spec = _pod_spec(obj)
    if spec is None:
        return False
    for field in ('containers', 'initContainers', 'ephemeralContainers'):
        containers = spec.get(field, [])
        if (not isinstance(containers, list) or (field == 'containers' and not containers)
                or any(not isinstance(c, dict) or not isinstance(c.get('name'), str)
                       or not LABEL.fullmatch(c['name'])
                       or not isinstance(c.get('image'), str) or not c['image']
                       for c in containers)):
            return False
    return True


def _flux_machine(obj):
    """Positive recognition only; unknown machinery still needs reviewed binding."""
    meta = obj['metadata']
    names = [meta['name']]
    refs = meta.get('ownerReferences', [])
    if isinstance(refs, list):
        names += [r.get('name', '') for r in refs if isinstance(r, dict)]
    labels = meta.get('labels', {})
    if isinstance(labels, dict):
        names += [labels.get(k, '') for k in ('app', 'app.kubernetes.io/name')]
    if any(isinstance(n, str) and any(n == f or n.startswith(f + '-')
                                    for f in FLUX_NAMES) for n in names):
        return True
    spec = _pod_spec(obj)
    if spec is None:
        return False
    for field in ('containers', 'initContainers', 'ephemeralContainers'):
        containers = spec.get(field, [])
        if isinstance(containers, list):
            for c in containers:
                if isinstance(c, dict) and isinstance(c.get('image'), str):
                    image = c['image'].rsplit('/', 1)[-1].split('@')[0].split(':')[0]
                    if image in FLUX_NAMES:
                        return True
    return False


class _Evaluation:
    def __init__(self):
        self.report = {
            'schema_version': 1, 'scope': 'offline-flux-state',
            'offline_only': True, 'runtime_authorization': False,
            'authenticity_established': False, 'freshness_established': False,
            'baseline_provenance_established': False,
            'outside_scope': ['native-stopped-world', 'native-cronjob-suspension',
                              'platform-node-storage', 'capacity-admission', 'live-acceptance'],
            'status': 'INCOMPLETE', 'complete': False,
            'observations': [], 'blocked': [], 'gaps': [], 'coverage': [],
        }

    def add(self, category, code, location, identity=None):
        entry = {'code': code, 'location': location}
        if identity is not None:
            entry['identity'] = identity
        self.report[category].append(entry)

    def gap(self, code, location, identity=None):
        self.add('gaps', code, location, identity)

    def capture(self, value, location, scope, kind, api):
        valid = True
        def invalid(code):
            nonlocal valid
            valid = False
            self.gap(code, location)
        if not isinstance(value, dict) or set(value) != {'status', 'complete', 'scope', 'list'}:
            invalid('CAPTURE_MALFORMED')
            self.report['coverage'].append({'location': location, 'complete': False})
            return [], False
        if value['status'] not in ('success', 'failed', 'missing'):
            invalid('CAPTURE_MALFORMED')
        elif value['status'] != 'success':
            invalid('LIST_FAILED' if value['status'] == 'failed' else 'LIST_MISSING')
        if value['complete'] is not True:
            invalid('LIST_PARTIAL')
        if value['scope'] != scope:
            invalid('LIST_SCOPE_MISMATCH')
        body = value['list']
        if not isinstance(body, dict):
            invalid('LIST_MALFORMED')
            items = []
        else:
            if not ((body.get('kind') == 'List' and body.get('apiVersion') == 'v1')
                    or (body.get('kind') == kind + 'List' and body.get('apiVersion') == api)):
                invalid('LIST_TYPE_MISMATCH')
            metadata = body.get('metadata')
            if not isinstance(metadata, dict):
                invalid('LIST_MALFORMED')
            else:
                token = metadata.get('continue', '')
                remaining = metadata.get('remainingItemCount', 0)
                if not isinstance(token, str) or type(remaining) is not int or remaining < 0:
                    invalid('LIST_MALFORMED')
                elif token or remaining:
                    invalid('LIST_PAGINATED')
            items = body.get('items')
            if not isinstance(items, list):
                invalid('LIST_MALFORMED')
                items = []
        self.report['coverage'].append({'location': location, 'complete': valid,
                                        'item_count': len(items)})
        return items, valid

    def baseline(self, value, native):
        location = 'baseline.native' if native else 'baseline.flux'
        result = {}
        uids = set()
        if not isinstance(value, list):
            self.gap('BASELINE_MALFORMED', location)
            return result
        for i, entry in enumerate(value):
            loc = f'{location}[{i}]'
            identity = _identity(entry)
            keys = IDENTITY_KEYS | ({'execution_sha256'} if native else set())
            if (identity is None or set(entry) != keys
                    or (native and (not isinstance(entry['execution_sha256'], str)
                                    or not HEX.fullmatch(entry['execution_sha256'])))):
                self.gap('BASELINE_MALFORMED', loc)
                continue
            parts = _gvr(identity['gvr'])
            expected_kind = NATIVE_GVRS.get(identity['gvr']) if native else SUPPORTED.get((parts[0], parts[2]))
            if identity['kind'] != expected_kind:
                self.gap('BASELINE_UNSUPPORTED', loc, identity)
            key = _key(identity)
            if key in result or identity['uid'] in uids:
                self.gap('BASELINE_DUPLICATE', loc, identity)
                continue
            result[key] = entry
            uids.add(identity['uid'])
        return result

    def records(self, value, location):
        result = {}
        if not isinstance(value, list):
            self.gap('RECORDS_MALFORMED', location)
            return result
        for i, entry in enumerate(value):
            loc = f'{location}[{i}]'
            if (not isinstance(entry, dict) or set(entry) != {'gvr', 'capture'}
                    or not _gvr(entry['gvr'])):
                self.gap('RECORD_MALFORMED', loc)
                continue
            # Keep duplicates for evaluation; they can never establish completeness.
            if entry['gvr'] in result:
                self.gap('LIST_DUPLICATE', loc)
            result.setdefault(entry['gvr'], []).append((loc, entry['capture']))
        return result

    def objects(self, items, gvr, kind, location):
        results = []
        seen, uids = set(), set()
        group, version, _ = _gvr(gvr)
        api = version if group == 'core' else group + '/' + version
        for i, obj in enumerate(items):
            loc = f'{location}.items[{i}]'
            if not isinstance(obj, dict) or not isinstance(obj.get('metadata'), dict):
                self.gap('OBJECT_MALFORMED', loc)
                continue
            identity = _identity(dict(gvr=gvr, kind=obj.get('kind'),
                                      **{k: obj['metadata'].get(k) for k in ('namespace', 'name', 'uid')}))
            if identity is None:
                self.gap('OBJECT_MALFORMED', loc)
                continue
            if obj.get('kind') != kind or obj.get('apiVersion') != api:
                self.gap('OBJECT_TYPE_MISMATCH', loc, identity)
                continue
            if _key(identity) in seen or identity['uid'] in uids:
                self.gap('OBJECT_DUPLICATE', loc, identity)
            seen.add(_key(identity)); uids.add(identity['uid'])
            results.append((loc, obj, identity))
        return results

    def inventory(self, capture):
        items, _ = self.capture(capture, 'captures.crds', 'cluster',
                                'CustomResourceDefinition', 'apiextensions.k8s.io/v1')
        inventory = {}
        names, uids = set(), set()
        for i, obj in enumerate(items):
            loc = f'captures.crds.items[{i}]'
            try:
                meta, spec = obj['metadata'], obj['spec']
                name, uid = meta['name'], meta['uid']
                group, plural, kind = spec['group'], spec['names']['plural'], spec['names']['kind']
                versions = spec['versions']
                valid = (obj['kind'] == 'CustomResourceDefinition'
                         and obj['apiVersion'] == 'apiextensions.k8s.io/v1'
                         and _dns(name) and isinstance(uid, str) and UID.fullmatch(uid)
                         and not meta.get('namespace') and _dns(group)
                         and isinstance(plural, str) and LABEL.fullmatch(plural)
                         and name == plural + '.' + group and isinstance(kind, str)
                         and KIND.fullmatch(kind) and isinstance(versions, list) and bool(versions)
                         and spec['scope'] in ('Namespaced', 'Cluster'))
                served, all_versions = [], set()
                for version in versions:
                    v = version['name']
                    valid = (valid and isinstance(v, str) and bool(VERSION.fullmatch(v))
                             and type(version['served']) is bool and type(version['storage']) is bool
                             and v not in all_versions)
                    all_versions.add(v)
                    if version['served'] is True:
                        served.append(v)
                valid = valid and bool(served) and sum(v['storage'] is True for v in versions) == 1
            except (KeyError, TypeError, AttributeError):
                valid = False
            if not valid:
                self.gap('CRD_MALFORMED', loc)
                continue
            if name in names or uid in uids:
                self.gap('CRD_DUPLICATE', loc)
            names.add(name); uids.add(uid)
            if group.endswith('.toolkit.fluxcd.io'):
                if spec['scope'] != 'Namespaced':
                    self.gap('FLUX_CRD_SCOPE_UNSUPPORTED', loc)
                inventory[(group, plural)] = (kind, served)
        return inventory

    def native(self, records, baseline):
        initial = len(self.report['gaps']), len(self.report['blocked'])
        seen = set()
        global_uids = set()
        for gvr in records:
            if gvr not in NATIVE_GVRS:
                self.gap('NATIVE_GVR_UNSUPPORTED', 'captures.native')
        for gvr, kind in NATIVE_GVRS.items():
            if gvr not in records:
                self.gap('LIST_MISSING', 'captures.native.' + kind)
                continue
            group, version, _ = _gvr(gvr)
            api = version if group == 'core' else group + '/' + version
            for loc, capture in records[gvr]:
                items, _ = self.capture(capture, loc, 'all-namespaces', kind, api)
                for objloc, obj, identity in self.objects(items, gvr, kind, loc):
                    key = _key(identity)
                    seen.add(key)
                    if identity['uid'] in global_uids:
                        self.gap('OBJECT_DUPLICATE', objloc, identity)
                    global_uids.add(identity['uid'])
                    shape_valid = _native_shape(obj)
                    if not shape_valid:
                        self.gap('NATIVE_OBJECT_MALFORMED', objloc, identity)
                    is_flux = _flux_machine(obj)
                    if is_flux:
                        self.add('blocked', 'FLUX_MACHINERY_PRESENT', objloc, identity)
                    expected = baseline.get(key)
                    if expected is None:
                        self.gap('NATIVE_UNBOUND', objloc, identity)
                    elif _identity(expected) != identity:
                        self.gap('IDENTITY_MISMATCH', objloc, identity)
                    elif not isinstance(obj.get('spec'), dict):
                        continue  # Shape gap above; no executable binding can be established.
                    elif _execution_digest(obj) != expected['execution_sha256']:
                        self.gap('NATIVE_EXECUTION_MISMATCH', objloc, identity)
                    elif shape_valid and not is_flux:
                        self.add('observations', 'REVIEWED_NON_FLUX_BINDING_MATCH', objloc, identity)
        for key, entry in baseline.items():
            if key not in seen:
                self.gap('EXPECTED_OBJECT_MISSING', 'baseline.native', _identity(entry))
        return initial == (len(self.report['gaps']), len(self.report['blocked']))

    def flux(self, records, baseline, inventory, native_absent):
        seen, selected, global_uids = set(), {}, set()
        for gvr, captures in records.items():
            group, version, plural = _gvr(gvr)
            crd = inventory.get((group, plural))
            if crd is None:
                self.gap('GVR_NOT_IN_INVENTORY', 'captures.flux')
                # Preserve coverage and sanitized available observations, never infer absence.
                for loc, capture in captures:
                    items, _ = self.capture(capture, loc, 'all-namespaces', 'Unknown', group + '/' + version)
                    for i, obj in enumerate(items):
                        if isinstance(obj, dict) and isinstance(obj.get('metadata'), dict):
                            identity = _identity(dict(gvr=gvr, kind=obj.get('kind'),
                                **{k: obj['metadata'].get(k) for k in ('namespace', 'name', 'uid')}))
                        else:
                            identity = None
                        self.gap('FLUX_KIND_UNSUPPORTED' if identity else 'OBJECT_MALFORMED',
                                 f'{loc}.items[{i}]', identity)
                continue
            kind, served = crd
            selected[(group, plural)] = selected.get((group, plural), 0) + len(captures)
            if version not in served:
                self.gap('GVR_VERSION_NOT_SERVED', 'captures.flux')
            for loc, capture in captures:
                items, complete = self.capture(capture, loc, 'all-namespaces', kind, group + '/' + version)
                if not items and complete:
                    self.add('observations', 'FLUX_LIST_EMPTY', loc)
                for objloc, obj, identity in self.objects(items, gvr, kind, loc):
                    key = _key(identity); seen.add(key)
                    if identity['uid'] in global_uids:
                        self.gap('OBJECT_DUPLICATE', objloc, identity)
                    global_uids.add(identity['uid'])
                    supported = SUPPORTED.get((group, plural)) == kind
                    if not supported:
                        self.gap('FLUX_KIND_UNSUPPORTED', objloc, identity)
                    expected = baseline.get(key)
                    matched = expected is not None and _identity(expected) == identity
                    if expected is None:
                        self.gap('FLUX_OBJECT_UNREVIEWED', objloc, identity)
                    elif not matched:
                        self.gap('IDENTITY_MISMATCH', objloc, identity)
                    if not supported:
                        continue
                    spec = obj.get('spec')
                    if not isinstance(spec, dict):
                        self.gap('FLUX_SPEC_MALFORMED', objloc, identity)
                        continue
                    suspend = spec.get('suspend')
                    if 'suspend' not in spec:
                        self.add('observations', 'SUSPEND_FIELD_ABSENT', objloc, identity)
                    elif type(suspend) is bool:
                        self.add('observations', 'SUSPEND_FIELD_TRUE' if suspend else 'SUSPEND_FIELD_FALSE',
                                 objloc, identity)
                    if 'suspend' in spec and type(suspend) is not bool:
                        self.gap('SUSPEND_NOT_BOOLEAN', objloc, identity)
                    elif kind == 'Kustomization':
                        self.add('observations' if suspend is True else 'blocked',
                                 'APPLY_INTENT_SUSPENDED' if suspend is True else 'APPLY_INTENT_NOT_SUSPENDED',
                                 objloc, identity)
                    elif suspend is True:
                        self.add('observations', 'FETCH_INTENT_SUSPENDED', objloc, identity)
                    elif native_absent and matched:
                        self.add('observations', 'FETCH_INTENT_CONDITIONALLY_INERT_NOT_DURABLY_SUSPENDED',
                                 objloc, identity)
                    else:
                        self.gap('FETCH_INERTNESS_UNCONFIRMED', objloc, identity)
        for crd in inventory:
            count = selected.get(crd, 0)
            if count != 1:
                self.gap('LIST_MISSING' if count == 0 else 'CRD_MULTIPLE_LISTS', 'captures.flux')
        for key, entry in baseline.items():
            if key not in seen:
                self.gap('EXPECTED_OBJECT_MISSING', 'baseline.flux', _identity(entry))

    def finish(self):
        self.report['complete'] = not self.report['gaps']
        self.report['status'] = ('BLOCKED' if self.report['blocked'] else
                                 'INCOMPLETE' if self.report['gaps'] else 'OK')
        return self.report


def evaluate(bundle):
    """Evaluate JSON-shaped saved evidence without IO or mutation; report all gaps."""
    ev = _Evaluation()
    if (not isinstance(bundle, dict) or set(bundle) != {'schema_version', 'baseline', 'captures'}
            or type(bundle.get('schema_version')) is not int or bundle['schema_version'] != 1):
        ev.gap('BUNDLE_MALFORMED', 'bundle')
    if not isinstance(bundle, dict):
        return ev.finish()
    baseline = bundle.get('baseline')
    if not isinstance(baseline, dict) or set(baseline) != {'flux', 'native'}:
        ev.gap('BASELINE_MALFORMED', 'baseline')
        baseline = baseline if isinstance(baseline, dict) else {}
    fb = ev.baseline(baseline.get('flux'), False)
    nb = ev.baseline(baseline.get('native'), True)
    captures = bundle.get('captures')
    if not isinstance(captures, dict) or set(captures) != {'crds', 'flux', 'native'}:
        ev.gap('CAPTURES_MALFORMED', 'captures')
        captures = captures if isinstance(captures, dict) else {}
    inventory = ev.inventory(captures.get('crds'))
    nr = ev.records(captures.get('native'), 'captures.native')
    fr = ev.records(captures.get('flux'), 'captures.flux')
    # Invalid baselines/record mappings must not establish conditional inertness.
    prior_gaps = bool(ev.report['gaps'])
    native_absent = ev.native(nr, nb) and not prior_gaps
    if native_absent:
        ev.add('observations', 'FLUX_ABSENCE_SUPPORTED_BY_REVIEWED_NATIVE_CAPTURE', 'captures.native')
    ev.flux(fr, fb, inventory, native_absent)
    return ev.finish()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate')
        result[key] = value
    return result


def main():
    """Bounded stdin only. No filenames, environment, collection, or writes."""
    ev = _Evaluation()
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            ev.gap('INPUT_TOO_LARGE', 'stdin')
            report = ev.finish()
        else:
            bundle = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
            report = evaluate(bundle)
    except (ValueError, UnicodeError, RecursionError):
        ev.gap('JSON_INVALID', 'stdin')
        report = ev.finish()
    except (TypeError, KeyError, AttributeError, OverflowError):
        ev.gap('INPUT_MALFORMED', 'stdin')
        report = ev.finish()
    except OSError:
        ev.gap('INPUT_READ_FAILED', 'stdin')
        report = ev.finish()
    sys.stdout.write(json.dumps(report, sort_keys=True) + '\n')
    return {'OK': 0, 'BLOCKED': 1, 'INCOMPLETE': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
