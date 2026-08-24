"""Cross-platform, process-scoped exclusive leases for workflow runs."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import BinaryIO

from .path_safety import UnsafeRunPathError, assert_safe_descendant, is_reparse


class RunLeaseError(RuntimeError):
    """The run lease cannot be acquired safely and exclusively."""


_PROCESS_LEASES: set[str] = set()
_PROCESS_LEASES_LOCK = threading.Lock()


def lease_path_for(run_dir: Path) -> Path:
    run_dir = Path(os.path.abspath(os.fspath(run_dir)))
    return run_dir.with_name(f".{run_dir.name}.lease")


class RunLease:
    """Hold one advisory lock until the workflow invocation returns."""

    def __init__(self, run_dir: Path) -> None:
        self.path = lease_path_for(run_dir)
        self._key = os.path.normcase(str(self.path))
        self._handle: BinaryIO | None = None

    def __enter__(self) -> "RunLease":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            assert_safe_descendant(
                self.path.parent, self.path, label="run lease path"
            )
            if (self.path.exists() or self.path.is_symlink()) and (
                not self.path.is_file() or is_reparse(self.path)
            ):
                raise RunLeaseError(
                    f"run lease path is not a safe regular file: {self.path}"
                )
        except UnsafeRunPathError as exc:
            raise RunLeaseError(str(exc)) from exc

        with _PROCESS_LEASES_LOCK:
            if self._key in _PROCESS_LEASES:
                raise RunLeaseError(
                    f"run is already active in another execution context: {self.path}"
                )
            _PROCESS_LEASES.add(self._key)

        try:
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.path, flags, 0o600)
            os.set_inheritable(descriptor, False)
            self._handle = os.fdopen(descriptor, "r+b", buffering=0)
            self._lock_nonblocking()
            return self
        except BaseException as exc:
            self._close_handle()
            with _PROCESS_LEASES_LOCK:
                _PROCESS_LEASES.discard(self._key)
            if isinstance(exc, RunLeaseError):
                raise
            raise RunLeaseError(
                f"cannot acquire exclusive run lease {self.path}: {exc}"
            ) from exc

    def _lock_nonblocking(self) -> None:
        assert self._handle is not None
        self._handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(
                    self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                )
        except OSError as exc:
            raise RunLeaseError(
                f"run is already active or its lease is unavailable: {self.path}"
            ) from exc

    def _unlock(self) -> None:
        assert self._handle is not None
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)

    def _close_handle(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if self._handle is not None:
                self._unlock()
        finally:
            self._close_handle()
            with _PROCESS_LEASES_LOCK:
                _PROCESS_LEASES.discard(self._key)
