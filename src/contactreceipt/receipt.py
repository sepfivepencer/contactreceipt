"""Receipt integrity verification without I/O or external dependencies."""

from __future__ import annotations

import hmac
import re
from typing import Any

from contactreceipt.canonical import canonical_sha256
from contactreceipt.errors import CanonicalizationError

_RECEIPT_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


def verify_receipt(value: Any) -> bool:
    """Verify ``receipt_id`` against the canonical receipt body.

    This checks content integrity only. It does not replace JSON Schema or
    semantic validation of the receipt fields.
    """
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return False
    receipt_id = value.get("receipt_id")
    if not isinstance(receipt_id, str) or _RECEIPT_ID.fullmatch(receipt_id) is None:
        return False
    body = dict(value)
    del body["receipt_id"]
    try:
        expected = f"sha256:{canonical_sha256(body)}"
    except CanonicalizationError:
        return False
    return hmac.compare_digest(receipt_id, expected)
