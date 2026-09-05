from __future__ import annotations

import math

import pytest

from contactreceipt.canonical import canonical_bytes, canonical_sha256
from contactreceipt.errors import CanonicalizationError
from contactreceipt.receipt import verify_receipt
from contactreceipt.schemas import schema_for


def test_canonical_bytes_sorts_keys_and_preserves_unicode() -> None:
    assert canonical_bytes({"z": 1, "a": "值"}) == '{"a":"值","z":1}'.encode()


def test_canonical_bytes_rejects_nan() -> None:
    with pytest.raises(CanonicalizationError, match="canonical JSON domain"):
        canonical_bytes({"value": math.nan})


@pytest.mark.parametrize("value", [{"bad": object()}, {"bad": "\ud800"}])
def test_canonical_bytes_wraps_domain_errors(value: object) -> None:
    with pytest.raises(CanonicalizationError, match="canonical JSON domain"):
        canonical_bytes(value)


def test_canonical_sha256_is_stable() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})


def test_schema_for_returns_defensive_copy() -> None:
    first = schema_for("trace")
    first["title"] = "changed"
    assert schema_for("trace")["title"] != "changed"


def test_schema_for_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown"):
        schema_for("unknown")


def test_receipt_schema_closes_every_declared_object() -> None:
    schema = schema_for("receipt")
    objects: list[dict[str, object]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                objects.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    assert len(objects) >= 10
    assert all(item.get("additionalProperties") is False for item in objects)
    assert all("required" in item and "properties" in item for item in objects)


def test_receipt_schema_has_nested_bounds() -> None:
    schema = schema_for("receipt")
    assert schema["properties"]["violations"]["maxItems"] == 1000
    assert schema["$defs"]["counts"]["properties"]["events"]["maximum"] == 100000
    replay = schema["$defs"]["failure_replay"]
    assert "end_index" in replay["required"]


def test_verify_receipt_accepts_valid_and_rejects_tampering() -> None:
    body = {"schema_version": "1.0", "verdict": "pass"}
    receipt = {**body, "receipt_id": f"sha256:{canonical_sha256(body)}"}
    assert verify_receipt(receipt) is True
    receipt["verdict"] = "fail"
    assert verify_receipt(receipt) is False


@pytest.mark.parametrize(
    "value",
    [None, {}, {"receipt_id": "bad"}, {"receipt_id": "sha256:" + "0" * 64, "x": math.nan}],
)
def test_verify_receipt_rejects_invalid_values(value: object) -> None:
    assert verify_receipt(value) is False
