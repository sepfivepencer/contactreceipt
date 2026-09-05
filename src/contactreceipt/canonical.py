"""Canonical JSON and content fingerprints."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from contactreceipt.errors import CanonicalizationError


def canonical_bytes(value: Any) -> bytes:
    """Encode a JSON-compatible value deterministically as UTF-8."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CanonicalizationError("value is outside the canonical JSON domain") from exc


def canonical_sha256(value: Any) -> str:
    """Return the lowercase SHA-256 of :func:`canonical_bytes`."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
