"""Domain-specific exceptions and terminal-safe display helpers."""

from __future__ import annotations

import json


class ContactReceiptError(Exception):
    """Base class for expected user-facing failures."""


class InputError(ContactReceiptError):
    """Raised when JSON input does not satisfy the neutral contract."""


class OutputError(ContactReceiptError):
    """Raised when an output cannot be published safely."""


class CanonicalizationError(ContactReceiptError):
    """Raised when a value is outside the supported canonical JSON domain."""


def safe_label(value: str, *, max_chars: int = 96) -> str:
    """Return a bounded ASCII JSON string suitable for an error message."""
    if max_chars < 8:
        raise ValueError("max_chars must be at least 8")
    result = '"'
    truncated = False
    for character in value:
        encoded = json.dumps(character, ensure_ascii=True)[1:-1]
        if len(result) + len(encoded) + len('..."') > max_chars:
            truncated = True
            break
        result += encoded
    if truncated:
        result += "..."
    return result + '"'
