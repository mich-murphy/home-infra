#!/usr/bin/env python3
"""Extract JSON schemas from checksum-locked upstream CRDs into a scratch directory.

Uses the same Gateway API artifacts as bootstrap, plus the exact Cilium release.
Kubernetes CEL/admission semantics still require live server-side dry-run tests.
No CRDs are installed by this helper. Downloads fail closed on digest mismatch.
"""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]


def strict_schema(value):
    if isinstance(value, dict):
        result = {k: strict_schema(v) for k, v in value.items() if k != "description"}
        if (result.get("type") == "object" and "properties" in result
                and not result.get("x-kubernetes-preserve-unknown-fields")):
            result.setdefault("additionalProperties", False)
        return result
    if isinstance(value, list):
        return [strict_schema(v) for v in value]
    return value


def main(destination):
    locks = [ROOT / "tests/kubernetes-proof-schemas.lock.json",
             ROOT / "kubernetes/bootstrap/artifacts.lock.json"]
    count = 0
    for lock in locks:
        for artifact in json.loads(lock.read_text())["artifacts"]:
            if not artifact["url"].endswith(".yaml"):
                continue
            with urllib.request.urlopen(artifact["url"], timeout=60) as response:
                raw = response.read()
            if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
                raise ValueError(f"Checksum mismatch: {artifact['url']}")
            crd = yaml.safe_load(raw)["spec"]
            for version in crd["versions"]:
                path = destination / crd["group"] / f"{crd['names']['kind'].lower()}_{version['name']}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                schema = strict_schema(version["schema"]["openAPIV3Schema"])
                path.write_text(json.dumps(schema) + "\n")
                count += 1
    print(f"Prepared {count} schemas from checksum-locked upstream CRDs")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
