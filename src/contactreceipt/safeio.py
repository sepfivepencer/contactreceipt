"""Bounded JSON reads and exclusive, atomic receipt publication."""

from __future__ import annotations

import json
import math
import os
import secrets
import stat
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import Any

from contactreceipt.canonical import canonical_bytes
from contactreceipt.errors import InputError, OutputError, safe_label

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_INTEGER_DIGITS = 100

_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


def _reject_constant(value: str) -> None:
    raise InputError(f"non-finite JSON number is not allowed: {safe_label(value)}")


def _parse_integer(value: str) -> int:
    digits = value.lstrip("-")
    if len(digits) > MAX_INTEGER_DIGITS:
        raise InputError("JSON integer has too many digits")
    try:
        return int(value)
    except ValueError as exc:
        raise InputError("invalid JSON integer") from exc


def _parse_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise InputError("invalid JSON number") from exc
    if not math.isfinite(parsed):
        raise InputError("non-finite JSON number is not allowed")
    return parsed


def _has_lone_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if _has_lone_surrogate(key):
            raise InputError("JSON object key contains a lone surrogate")
        if key in result:
            raise InputError(f"duplicate JSON key: {safe_label(key)}")
        result[key] = value
    return result


def _validate_unicode(value: Any) -> None:
    if isinstance(value, str):
        if _has_lone_surrogate(value):
            raise InputError("JSON string contains a lone surrogate")
        return
    if isinstance(value, list):
        for item in value:
            _validate_unicode(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if _has_lone_surrogate(key):
                raise InputError("JSON object key contains a lone surrogate")
            _validate_unicode(item)


def load_json(path: Path, *, max_bytes: int = MAX_INPUT_BYTES) -> Any:
    """Read one regular UTF-8 JSON file without following a final symlink."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    label = safe_label(path.name)
    try:
        fd = os.open(path, flags)
    except (OSError, ValueError) as exc:
        raise InputError(f"cannot open input file: {label}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise InputError(f"input is not a regular file: {label}")
        if info.st_size > max_bytes:
            raise InputError(f"input exceeds {max_bytes} bytes: {label}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_bytes:
            raise InputError(f"input exceeds {max_bytes} bytes: {label}")
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError(f"input is not UTF-8 JSON: {label}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_int=_parse_integer,
            parse_float=_parse_float,
        )
        _validate_unicode(value)
        return value
    except InputError:
        raise
    except (ValueError, RecursionError) as exc:
        raise InputError(f"invalid JSON: {label}") from exc


def _open_parent(path: Path) -> tuple[int, os.stat_result]:
    """Open every parent component without following symlinks."""
    parent = path.parent
    start = os.sep if parent.is_absolute() else "."
    try:
        current_fd = os.open(start, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise OutputError("cannot open output parent directory") from exc
    try:
        for component in parent.parts:
            if component in {os.sep, ".", ""}:
                continue
            if component == "..":
                raise OutputError("output parent must not contain '..'")
            child_fd = -1
            try:
                child_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=current_fd)
                named = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                opened = os.fstat(child_fd)
            except (OSError, ValueError) as exc:
                if child_fd >= 0:
                    os.close(child_fd)
                raise OutputError("output parent directory does not exist or is unsafe") from exc
            if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                os.close(child_fd)
                raise OutputError("output parent directory changed while opening")
            os.close(current_fd)
            current_fd = child_fd
        return current_fd, os.fstat(current_fd)
    except BaseException:
        os.close(current_fd)
        raise


class JsonOutput:
    """One output transaction anchored to a single verified directory FD."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.name
        self._dir_fd = -1
        self._parent_info: os.stat_result | None = None
        self._temp_name: str | None = None
        self._published_info: os.stat_result | None = None
        self._committed = False

    def __enter__(self) -> JsonOutput:
        if self.name in {"", ".", ".."}:
            raise OutputError("output must name a file")
        self._dir_fd, self._parent_info = _open_parent(self.path)
        try:
            self._assert_parent_current()
            try:
                os.stat(self.name, dir_fd=self._dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                return self
            except (OSError, ValueError) as exc:
                raise OutputError(
                    f"cannot inspect output destination: {safe_label(self.name)}"
                ) from exc
            raise OutputError(f"refusing to overwrite output: {safe_label(self.name)}")
        except BaseException:
            os.close(self._dir_fd)
            self._dir_fd = -1
            raise

    def _assert_parent_current(self) -> None:
        if self._parent_info is None:
            raise OutputError("output transaction is not open")
        check_fd, check_info = _open_parent(self.path)
        os.close(check_fd)
        expected = (self._parent_info.st_dev, self._parent_info.st_ino)
        if (check_info.st_dev, check_info.st_ino) != expected:
            raise OutputError("output parent directory changed during publication")

    def _unlink_published_if_owned(self) -> None:
        if self._published_info is None or self._dir_fd < 0:
            return
        try:
            current = os.stat(self.name, dir_fd=self._dir_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (
                self._published_info.st_dev,
                self._published_info.st_ino,
            ):
                os.unlink(self.name, dir_fd=self._dir_fd)
        except FileNotFoundError:
            pass

    def write_json(self, value: Any) -> None:
        """Canonicalize and publish one JSON value exactly once."""
        if self._dir_fd < 0 or self._committed:
            raise OutputError("output transaction is not writable")
        payload = canonical_bytes(value) + b"\n"
        if len(payload) > MAX_OUTPUT_BYTES:
            raise OutputError(f"output exceeds {MAX_OUTPUT_BYTES} bytes")
        self._assert_parent_current()
        self._temp_name = f".{self.name}.tmp-{secrets.token_hex(8)}"
        temp_fd = -1
        try:
            create_flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            temp_fd = os.open(self._temp_name, create_flags, 0o600, dir_fd=self._dir_fd)
            view = memoryview(payload)
            while view:
                written = os.write(temp_fd, view)
                if written <= 0:
                    raise OutputError("failed to write complete output")
                view = view[written:]
            os.fsync(temp_fd)
            temp_info = os.fstat(temp_fd)
            os.close(temp_fd)
            temp_fd = -1
            self._assert_parent_current()
            try:
                os.link(
                    self._temp_name,
                    self.name,
                    src_dir_fd=self._dir_fd,
                    dst_dir_fd=self._dir_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise OutputError(f"refusing to overwrite output: {safe_label(self.name)}") from exc
            self._published_info = temp_info
            published = os.stat(self.name, dir_fd=self._dir_fd, follow_symlinks=False)
            if (published.st_dev, published.st_ino) != (temp_info.st_dev, temp_info.st_ino):
                raise OutputError("published output identity mismatch")
            self._published_info = published
            self._assert_parent_current()
            os.fsync(self._dir_fd)
            self._committed = True
        except OutputError:
            self._unlink_published_if_owned()
            raise
        except OSError as exc:
            self._unlink_published_if_owned()
            raise OutputError(f"cannot publish output: {safe_label(self.name)}") from exc
        finally:
            if temp_fd >= 0:
                os.close(temp_fd)
            if self._temp_name is not None:
                with suppress(FileNotFoundError):
                    os.unlink(self._temp_name, dir_fd=self._dir_fd)
                self._temp_name = None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None and not self._committed:
            self._unlink_published_if_owned()
        if self._dir_fd >= 0:
            os.close(self._dir_fd)
            self._dir_fd = -1


def open_json_output(path: Path) -> JsonOutput:
    """Return a fail-closed output transaction for ``path``."""
    return JsonOutput(path)


def ensure_output_available(path: Path) -> None:
    """Check availability using the same secure transaction implementation."""
    with open_json_output(path):
        pass


def safe_write_json(path: Path, value: Any) -> None:
    """Publish canonical JSON atomically and exclusively with mode ``0600``."""
    with open_json_output(path) as output:
        output.write_json(value)
