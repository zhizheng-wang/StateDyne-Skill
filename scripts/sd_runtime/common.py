"""Strict JSON, atomic files, integrity stamps and a single-controller lock."""
from __future__ import annotations
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any

class StateDyneError(Exception):
    """A user-correctable execution error; never implies semantic failure/success."""

class PendingJobs(StateDyneError):
    pass


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise StateDyneError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(
                              StateDyneError(f"Non-finite JSON number: {x}")))
    except (ValueError, TypeError, RecursionError) as exc:
        raise StateDyneError(f"Invalid JSON: {exc}") from exc


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".sd-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_json(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2,
                                 allow_nan=False) + "\n")


def within(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise StateDyneError("Path escapes the run directory")
    return target


@contextlib.contextmanager
def controller_lock(root: Path):
    """Fail closed on a stale lock; never steal a possibly active controller."""
    path = root / ".controller.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise StateDyneError("Run is locked. If a controller crashed, confirm it is no longer running before removing .controller.lock.") from exc
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
