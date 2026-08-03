"""Load root-owned deployment variables from the Docker host secret bind."""

from __future__ import annotations

import os
from pathlib import Path


SECRET_PATH = Path("/run/secrets/ai-observability.env")


def load() -> None:
    for line in SECRET_PATH.read_text().splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key:
            raise RuntimeError(f"invalid deployment variable in {SECRET_PATH}")
        os.environ.setdefault(key, value)
