#!/usr/bin/env python3
"""Fail-closed safety checks on rendered application manifests (not live proof).

Usage: kubectl kustomize kubernetes/apps/<group> | python3 tests/kubernetes-proof.py
This intentionally checks the isolated proof profile, not a future production overlay.
"""
import ipaddress
import re
import sys

import yaml


def check(documents):
    errors = []
    workloads = 0

    def require(condition, name, message):
        if not condition:
            errors.append(f"{name}: {message}")

    for doc in documents:
        if not doc:
            continue
        kind = doc.get("kind", "")
        meta = doc.get("metadata", {})
        name = f"{kind}/{meta.get('namespace', '')}/{meta.get('name', '')}"
        spec = doc.get("spec", {})
        if kind == "Namespace":
            require(meta.get("name", "").startswith("proof-"), name, "namespace must be proof-scoped")
            require(meta.get("labels", {}).get("app.kubernetes.io/part-of") == "talos-proof", name, "missing isolation selector label")
        elif kind not in {"PersistentVolume", "ClusterRole", "ClusterRoleBinding", "CustomResourceDefinition"}:
            require(meta.get("namespace", "").startswith("proof-"), name, "resource must have an explicit proof namespace")
        else:
            require(False, name, "application must not create cluster-scoped infrastructure/RBAC")
        if kind == "Secret":
            require(False, name, "generate proof credentials privately; do not render committed Secrets")
        if kind == "PersistentVolumeClaim":
            require(spec.get("storageClassName") == "proof-local", name, "must use dedicated proof-local storage")
        if kind == "Service":
            require(spec.get("type", "ClusterIP") == "ClusterIP", name, "apps must not expose host/NodePort/LoadBalancer ports")
            require(not spec.get("externalIPs") and not spec.get("externalName"), name, "external production routing forbidden")
        if kind == "HTTPRoute":
            for host in spec.get("hostnames", []):
                require(host.endswith(".test") or host.endswith(".invalid"), name, "use reserved test hostnames, not production DNS")
        if kind == "NetworkPolicy":
            for rule in spec.get("egress", []):
                require(bool(rule.get("to")), name, "unrestricted egress forbidden")
                for peer in rule.get("to", []):
                    require(bool(peer), name, "empty egress peer permits all traffic")
                    block = peer.get("ipBlock")
                    if block:
                        try:
                            network = ipaddress.ip_network(block["cidr"])
                            require(network.is_global, name, "egress IP blocks may not target private/production ranges")
                        except (ValueError, KeyError):
                            require(False, name, "invalid egress CIDR")
        template = None
        if kind in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
            require(kind not in {"DaemonSet", "Job"}, name, "proof apps must be explicitly activated Deployments/StatefulSets/suspended CronJobs")
            require(spec.get("replicas") == 0, name, "default proof workloads must be scaled to zero for bounded resource use")
            template = spec.get("template", {}).get("spec", {})
        elif kind == "CronJob":
            require(spec.get("suspend") is True, name, "proof schedules must default suspended")
            template = spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
        elif kind == "Pod":
            require(False, name, "unmanaged application Pod forbidden")
        if template is None:
            continue
        workloads += 1
        require(template.get("automountServiceAccountToken") is False, name, "disable unnecessary API credentials")
        for flag in ("hostNetwork", "hostPID", "hostIPC"):
            require(not template.get(flag), name, f"{flag} forbidden")
        require(not template.get("nodeName"), name, "use scheduler, not nodeName")
        for volume in template.get("volumes", []):
            require("hostPath" not in volume and "nfs" not in volume, name, "no production/host filesystem mounts")
        for container in template.get("containers", []) + template.get("initContainers", []):
            cname = f"{name}/{container.get('name', '?')}"
            require(bool(re.fullmatch(r".+@sha256:[0-9a-f]{64}", container.get("image", ""))), cname, "image must be immutable sha256 digest")
            resources = container.get("resources", {})
            require(all(resources.get("requests", {}).get(k) for k in ("cpu", "memory")), cname, "CPU/memory requests required")
            require(bool(resources.get("limits", {}).get("memory")), cname, "memory limit required")
            security = container.get("securityContext", {})
            require(not security.get("privileged"), cname, "privileged application forbidden")
            require("ALL" in security.get("capabilities", {}).get("drop", []), cname, "drop ALL capabilities before explicit exceptions")
            require((security.get("seccompProfile") or template.get("securityContext", {}).get("seccompProfile", {})).get("type") == "RuntimeDefault", cname, "RuntimeDefault seccomp required")
            for port in container.get("ports", []):
                require(not port.get("hostPort"), cname, "hostPort forbidden")
            if kind in {"Deployment", "StatefulSet"} and container in template.get("containers", []):
                require(bool(container.get("readinessProbe")), cname, "readiness probe required")
                require(bool(container.get("livenessProbe")), cname, "liveness probe required")
    require(workloads > 0, "render", "no application workloads found")
    return errors


if __name__ == "__main__":
    try:
        errors = check(list(yaml.safe_load_all(sys.stdin)))
    except yaml.YAMLError as exc:
        print(f"Invalid YAML: {exc}", file=sys.stderr)
        sys.exit(1)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    print("Proof application safety checks passed (static checks, not runtime acceptance).")
