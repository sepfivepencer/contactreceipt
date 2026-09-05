from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest

from contactreceipt.errors import InputError
from contactreceipt.model import (
    evidence_as_dict,
    parse_evidence,
    parse_policy,
    parse_trace,
    policy_as_dict,
    trace_as_dict,
)


def test_parse_examples_round_trip(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    assert trace_as_dict(parse_trace(trace_data)) == trace_data
    normalized_policy = policy_as_dict(parse_policy(policy_data))
    assert normalized_policy["assembly_id"] == policy_data["assembly_id"]
    normalized_evidence = evidence_as_dict(parse_evidence(evidence_data))
    assert evidence_as_dict(parse_evidence(normalized_evidence)) == normalized_evidence


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("run_id", "bad/id"),
        ("environment", "robot"),
        ("source_format", "csv"),
        ("events", []),
        ("extra", 1),
    ],
)
def test_trace_rejects_bad_root_fields(
    trace_data: dict[str, Any], field: str, value: object
) -> None:
    trace_data[field] = value
    with pytest.raises(InputError):
        parse_trace(trace_data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seq", True),
        ("seq", -1),
        ("t_ns", -1),
        ("kind", "teleport"),
        ("phase", "bad phase"),
        ("contact_state", "crash"),
        ("force_n", [1, 2]),
        ("force_n", [1, float("inf"), 2]),
        ("torque_nm", [1, True, 2]),
        ("evidence_refs", ["same", "same"]),
    ],
)
def test_trace_rejects_bad_event_values(
    trace_data: dict[str, Any], field: str, value: object
) -> None:
    trace_data["events"][0][field] = value
    with pytest.raises(InputError):
        parse_trace(trace_data)


def test_trace_rejects_missing_event_field(trace_data: dict[str, Any]) -> None:
    del trace_data["events"][0]["kind"]
    with pytest.raises(InputError, match="missing field"):
        parse_trace(trace_data)


def test_trace_rejects_uppercase_digest(trace_data: dict[str, Any]) -> None:
    trace_data["source_artifact_sha256"] = "A" * 64
    with pytest.raises(InputError):
        parse_trace(trace_data)


def test_direct_parser_rejects_lone_surrogate_string(trace_data: dict[str, Any]) -> None:
    trace_data["run_id"] = "bad\ud800"
    with pytest.raises(InputError):
        parse_trace(trace_data)


def test_direct_parser_rejects_lone_surrogate_key(trace_data: dict[str, Any]) -> None:
    trace_data["bad\ud800"] = 1
    with pytest.raises(InputError, match="lone surrogate"):
        parse_trace(trace_data)


def test_unknown_key_error_escapes_terminal_control(trace_data: dict[str, Any]) -> None:
    trace_data["bad\x1b\nkey"] = 1
    with pytest.raises(InputError) as caught:
        parse_trace(trace_data)
    message = str(caught.value)
    assert "\x1b" not in message
    assert "\n" not in message
    assert "\\u001b" in message
    assert "\\n" in message


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("initial_phase",), "missing"),
        (("terminal_phase",), "missing"),
        (("phases", 0, "requires"), ["missing"]),
        (("phases", 0, "allowed_next"), ["missing"]),
        (("phases", 0, "required_kinds"), ["teleport"]),
        (("phases", 0, "max_duration_ns"), 0),
        (("phases", 0, "envelope", "allowed_contact_states"), []),
        (("phases", 0, "envelope", "force_norm_max_n"), 0),
        (("phases", 0, "envelope", "force_abs_max_n"), [1, -1, 1]),
        (("evidence_requirements", 0, "kind"), "photograph"),
        (("evidence_requirements", 0, "environments"), []),
        (("evidence_requirements", 0, "min_count"), 0),
    ],
)
def test_policy_rejects_invalid_values(
    policy_data: dict[str, Any], path: tuple[object, ...], value: object
) -> None:
    target: Any = policy_data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(InputError):
        parse_policy(policy_data)


def test_policy_rejects_duplicate_phase(policy_data: dict[str, Any]) -> None:
    policy_data["phases"].append(deepcopy(policy_data["phases"][0]))
    with pytest.raises(InputError, match="unique"):
        parse_policy(policy_data)


def test_policy_rejects_self_reference(policy_data: dict[str, Any]) -> None:
    policy_data["phases"][0]["requires"] = ["approach"]
    with pytest.raises(InputError, match="self-reference"):
        parse_policy(policy_data)


def test_policy_rejects_prerequisite_cycle(policy_data: dict[str, Any]) -> None:
    policy_data["phases"][0]["requires"] = ["mate"]
    with pytest.raises(InputError, match="acyclic"):
        parse_policy(policy_data)


def test_policy_rejects_initial_phase_prerequisite(policy_data: dict[str, Any]) -> None:
    policy_data["phases"][0]["requires"] = ["mate"]
    policy_data["phases"][1]["requires"] = []
    with pytest.raises(InputError, match="initial phase"):
        parse_policy(policy_data)


def test_policy_rejects_unreachable_terminal(policy_data: dict[str, Any]) -> None:
    policy_data["phases"][1]["allowed_next"] = []
    with pytest.raises(InputError, match="reachable"):
        parse_policy(policy_data)


def test_policy_rejects_terminal_successor(policy_data: dict[str, Any]) -> None:
    policy_data["phases"][2]["allowed_next"] = ["approach"]
    with pytest.raises(InputError, match="terminal phase"):
        parse_policy(policy_data)


def test_policy_rejects_duplicate_requirement(policy_data: dict[str, Any]) -> None:
    policy_data["evidence_requirements"].append(deepcopy(policy_data["evidence_requirements"][0]))
    with pytest.raises(InputError, match="unique"):
        parse_policy(policy_data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "bad/id"),
        ("kind", "photo"),
        ("sha256", "0" * 63),
        ("applies_to", []),
        ("applies_to", ["simulation", "simulation"]),
        ("source_uri", "contains\nnewline"),
    ],
)
def test_evidence_rejects_bad_item(
    evidence_data: dict[str, Any], field: str, value: object
) -> None:
    evidence_data["items"][0][field] = value
    with pytest.raises(InputError):
        parse_evidence(evidence_data)


def test_evidence_rejects_duplicate_id(evidence_data: dict[str, Any]) -> None:
    evidence_data["items"][1]["id"] = evidence_data["items"][0]["id"]
    with pytest.raises(InputError, match="unique"):
        parse_evidence(evidence_data)


@pytest.mark.parametrize("parser", [parse_trace, parse_policy, parse_evidence])
def test_parsers_require_object_roots(parser: Callable[[Any], object]) -> None:
    with pytest.raises(InputError, match="object"):
        parser([])
