"""Cross-process lock shared by client Compose and recovery operations."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

RECOVERY_LOCK_FILE = ".client-recovery-operation.lock"


@contextmanager
def recovery_operation_lock(compose_dir: Path):
    """Serialize operations using a persistent lock file and an OS-held lock."""
    compose_dir = compose_dir.resolve(strict=True)
    lock_path = compose_dir / RECOVERY_LOCK_FILE
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
