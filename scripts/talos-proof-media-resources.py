"""Pure exact resource oracle; no safety imports or runtime calls."""
import re

MIB = 1024 * 1024


def quantity(value, resource):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('unsupported resource quantity')
    value = str(value)
    pattern = r'([0-9]+)(Ki|Mi|Gi|Ti)?' if resource == 'memory' else r'([0-9]+)(m)?'
    match = re.fullmatch(pattern, value)
    if not match or int(match[1]) <= 0:
        raise ValueError('unsupported or nonpositive ' + resource + ' quantity')
    if resource == 'memory':
        return int(match[1]) * {None: 1, 'Ki': 1024, 'Mi': MIB, 'Gi': 1024**3, 'Ti': 1024**4}[match[2]]
    return int(match[1]) * (1 if match[2] == 'm' else 1000)


def effective_limits(pod):
    if any(k in pod for k in ('overhead', 'resources', 'ephemeralContainers')):
        raise ValueError('unsupported pod-level/ephemeral resources; review explicitly')
    containers = pod.get('containers', [])
    if not containers:
        raise ValueError('regular container required')
    names = set()
    def limits(c, init=False):
        if not c.get('name') or c['name'] in names:
            raise ValueError('missing/duplicate container name')
        names.add(c['name'])
        if ('restartPolicy' in c and (not init or c['restartPolicy'] != 'Always')):
            raise ValueError('unsupported container restart policy')
        try:
            values = c['resources']['limits']
            if set(values) != {'cpu', 'memory'}:
                raise ValueError('unsupported or missing limits')
            return {r: quantity(values[r], r) for r in ('cpu', 'memory')}
        except KeyError as exc:
            raise ValueError('every container/init needs explicit cpu+memory limits') from exc
    regular = [limits(c) for c in containers]
    steady = {r: sum(c[r] for c in regular) for r in ('cpu', 'memory')}
    prefix = dict(cpu=0, memory=0)
    peak = dict(cpu=0, memory=0)
    for c in pod.get('initContainers', []):
        current = limits(c, init=True)
        for r in peak:
            # All prior restartable init sidecars are concurrent with this init.
            peak[r] = max(peak[r], prefix[r] + current[r])
        if c.get('restartPolicy') == 'Always':
            for r in prefix:
                prefix[r] += current[r]
    return {r: max(peak[r], steady[r] + prefix[r]) for r in peak}


def assert_charge(pod, charged_mib):
    actual = effective_limits(pod)['memory']
    if actual > charged_mib * MIB:
        raise ValueError('undercharged effective pod memory')
    return actual




def pinchflat_budget(template, receipt):
    """Validate actual selected live template, including stopped retained profiles."""
    annotations = template.get('metadata', {}).get('annotations', {})
    pod = template['spec']
    profile = annotations.get('talos-proof.home/provider-fixture')
    marker = annotations.get('talos-proof.home/pinchflat-main-memory-mib')
    containers = pod.get('containers', [])
    names = [c.get('name') for c in containers]
    provider = bool(profile or marker or 'rss-fixture' in names)
    if provider:
        if profile != 'pinchflat-rss' or marker != '384' or sorted(names) != ['pinchflat', 'rss-fixture']:
            raise RuntimeError('unknown or inconsistent Pinchflat provider profile')
        require_pinchflat_384(receipt)
    elif names != ['pinchflat']:
        raise RuntimeError('unknown Pinchflat base container profile')
    approved = {'pinchflat': {'requests': {'cpu': '50m', 'memory': '128Mi'},
                             'limits': {'cpu': '1000m', 'memory': '384Mi' if provider else '256Mi'}}}
    if provider:
        approved['rss-fixture'] = {'requests': {'cpu': '10m', 'memory': '32Mi'},
                                   'limits': {'cpu': '200m', 'memory': '128Mi'}}
    try:
        ceiling = effective_limits(pod)['memory']
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('invalid Pinchflat effective resource ceiling') from exc
    budget = 512 if provider else 256
    if ceiling != budget * MIB or pod.get('initContainers') or any(c.get('resources') != approved[c['name']] for c in containers):
        raise RuntimeError('Pinchflat resource/profile drift from explicit approved ceiling')
    return budget


def require_pinchflat_384(receipt):
    if receipt.get('provider_fixture') != 'pinchflat-rss':
        raise RuntimeError('provider requires exact parent receipt provider_fixture=pinchflat-rss')
    if type(receipt.get('pinchflat_main_memory_mib')) is not int or receipt['pinchflat_main_memory_mib'] != 384:
        raise RuntimeError('provider requires explicit approved pinchflat_main_memory_mib=384')


def pinchflat_no_restart(pods):
    """No known OOM/restart retry in a newly granted experiment incarnation."""
    for pod in pods:
        for status in pod.get('status', {}).get('initContainerStatuses', []) + pod.get('status', {}).get('containerStatuses', []):
            if status.get('restartCount', 0) or status.get('lastState', {}).get('terminated') or status.get('state', {}).get('terminated'):
                raise RuntimeError('Pinchflat experiment termination/restart: STOP, no retry authorized')
