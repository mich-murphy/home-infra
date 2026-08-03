#!/usr/bin/env python3
"""Take consistent, retained backups of MLflow SQLite state and artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sqlite3
import tarfile
import time
from pathlib import Path


SOURCE = Path("/mlflow")
TARGET = Path("/backups")


def snapshot() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    temporary = TARGET / f".{stamp}.tmp"
    final = TARGET / stamp
    temporary.mkdir(parents=True, exist_ok=False)
    for name in ("mlflow.db", "auth.db"):
        source = SOURCE / name
        if source.exists():
            with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db, sqlite3.connect(temporary / name) as backup_db:
                source_db.backup(backup_db)
                if backup_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError(f"integrity check failed for {name}")
    with tarfile.open(temporary / "files.tar.gz", "w:gz") as archive:
        for name in ("artifacts", "trace-archive"):
            path = SOURCE / name
            if path.exists():
                archive.add(path, arcname=name, recursive=True)
    temporary.rename(final)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(os.environ.get("MLFLOW_BACKUP_RETENTION_DAYS", "14")))
    for child in TARGET.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            try:
                created = dt.datetime.strptime(child.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
            except ValueError:
                continue
            if created < cutoff:
                shutil.rmtree(child)
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    while True:
        print(f"MLflow backup complete: {snapshot()}", flush=True)
        if args.once:
            return 0
        time.sleep(int(os.environ.get("MLFLOW_BACKUP_INTERVAL_SECONDS", "86400")))


if __name__ == "__main__":
    raise SystemExit(main())
