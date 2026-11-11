#!/usr/bin/env python3
"""Regression tests ensure proof-profile safety gates reject dangerous mutations."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("proof", Path(__file__).with_name("kubernetes-proof.py"))
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


class ProofSafetyTests(unittest.TestCase):
    def setUp(self):
        self.document = {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": "fixture", "namespace": "proof-fixture"},
            "spec": {"replicas": 0, "template": {"spec": {
                "automountServiceAccountToken": False,
                "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{
                    "name": "fixture", "image": "example.invalid/fixture@sha256:" + "a" * 64,
                    "resources": {"requests": {"cpu": "10m", "memory": "16Mi"}, "limits": {"memory": "32Mi"}},
                    "securityContext": {"capabilities": {"drop": ["ALL"]}},
                    "readinessProbe": {"tcpSocket": {"port": 8080}},
                    "livenessProbe": {"tcpSocket": {"port": 8080}},
                }],
            }}},
        }

    def test_safe_fixture(self):
        self.assertEqual([], proof.check([self.document]))

    def test_unsafe_workload_mutations(self):
        changes = [
            (lambda d: d["metadata"].update(namespace="default"), "proof namespace"),
            (lambda d: d["spec"].update(replicas=1), "scaled to zero"),
            (lambda d: d["spec"]["template"]["spec"].update(hostNetwork=True), "hostNetwork"),
            (lambda d: d["spec"]["template"]["spec"].update(automountServiceAccountToken=True), "API credentials"),
            (lambda d: d["spec"]["template"]["spec"].update(volumes=[{"nfs": {"server": "10.77.20.101", "path": "/production"}}]), "filesystem mounts"),
            (lambda d: d["spec"]["template"]["spec"]["containers"][0].update(image="example:latest"), "immutable"),
            (lambda d: d["spec"]["template"]["spec"]["containers"][0].update(resources={}), "requests"),
            (lambda d: d["spec"]["template"]["spec"]["containers"][0]["securityContext"].update(privileged=True), "privileged"),
        ]
        for mutate, expected in changes:
            with self.subTest(expected=expected):
                doc = copy.deepcopy(self.document)
                mutate(doc)
                self.assertIn(expected, "\n".join(proof.check([doc])))

    def test_dangerous_resources(self):
        cases = [
            ({"kind": "Secret", "stringData": {"password": "do-not-commit"}}, "credentials"),
            ({"kind": "Service", "spec": {"type": "LoadBalancer"}}, "expose"),
            ({"kind": "PersistentVolumeClaim", "spec": {"storageClassName": "production"}}, "proof-local"),
            ({"kind": "NetworkPolicy", "spec": {"egress": [{}]}}, "unrestricted egress"),
            ({"kind": "NetworkPolicy", "spec": {"egress": [{"to": [{}]}]}}, "empty egress peer"),
            ({"kind": "NetworkPolicy", "spec": {"egress": [{"to": [{"ipBlock": {"cidr": "10.77.0.0/16"}}]}]}}, "private/production"),
            ({"kind": "HTTPRoute", "spec": {"hostnames": ["nextcloud.local.elmurphy.com"]}}, "reserved test"),
        ]
        for resource, expected in cases:
            with self.subTest(expected=expected):
                resource["metadata"] = {"name": "unsafe", "namespace": "proof-fixture"}
                self.assertIn(expected, "\n".join(proof.check([self.document, resource])))

    def test_empty_input_is_not_success(self):
        self.assertTrue(proof.check([]))


if __name__ == "__main__":
    unittest.main()
