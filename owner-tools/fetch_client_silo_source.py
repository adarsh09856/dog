#!/usr/bin/env python3
"""Fetch the checksum-pinned PGSTY Silo source archive for client releases."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SILO_RELEASE = "RELEASE.2026-10-26T00-00-00Z"
SILO_SOURCE_URL = (
    "https://github.com/pgsty/silo/archive/refs/tags/"
    f"{SILO_RELEASE}.tar.gz"
)
SILO_SOURCE_SHA256 = "011653445e59b3d9f01ca482a41e1706ba214d5cac4c254b43543b4fe8d209fc"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
DOWNLOAD_TIMEOUT = 60


def fetch_source_archive(output: Path) -> str:
    """Download only the approved source and publish it after digest validation."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if output.is_symlink() or not output.is_file() or output.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("Existing PGSTY Silo source archive is not a supported regular file")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        if digest == SILO_SOURCE_SHA256:
            return digest
        raise ValueError("Existing PGSTY Silo source archive has an unexpected digest")

    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        digest = hashlib.sha256()
        total = 0
        request = urllib.request.Request(
            SILO_SOURCE_URL,
            headers={"User-Agent": "KodewavesClientRelease/1"},
        )
        with os.fdopen(fd, "wb") as destination:
            try:
                with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > MAX_SOURCE_BYTES:
                            raise ValueError("PGSTY Silo source archive exceeds the supported size")
                        digest.update(block)
                        destination.write(block)
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                raise ValueError("Unable to download the approved PGSTY Silo source archive") from exc
            destination.flush()
            os.fsync(destination.fileno())
        actual = digest.hexdigest()
        if actual != SILO_SOURCE_SHA256:
            raise ValueError("PGSTY Silo source archive failed its pinned SHA-256 check")
        os.link(temporary, output)
        temporary.unlink()
        return actual
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(f"Verified PGSTY Silo source archive: {fetch_source_archive(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
