from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from contactreceipt.canonical import canonical_bytes, canonical_sha256
from contactreceipt.engine import audit
from contactreceipt.model import event_as_dict, parse_evidence, parse_policy, parse_trace


def _audit(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> dict[str, Any]:
    return audit(parse_trace(trace_data), parse_policy(policy_data), parse_evidence(evidence_data))


def _codes(receipt: dict[str, Any]) -> list[str]:
    return [item["code"] for item in receipt["violations"]]


def test_passing_trace_has_content_addressed_receipt(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    receipt = _audit(trace_data, policy_data, evidence_data)
    assert receipt["verdict"] == "pass"
    assert receipt["counts"] == {
        "events": 10,
        "phases_completed": 3,
        "violations": 0,
        "violations_truncated": False,
    }
    assert receipt["failure_replay"] is None
    expected = deepcopy(receipt)
    receipt_id = expected.pop("receipt_id")
    assert receipt_id == f"sha256:{canonical_sha256(expected)}"


def test_receipt_is_byte_stable(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    first = _audit(trace_data, policy_data, evidence_data)
    second = _audit(deepcopy(trace_data), deepcopy(policy_data), deepcopy(evidence_data))
    assert canonical_bytes(first) == canonical_bytes(second)
    assert "generated_at" not in first


def test_object_key_order_does_not_change_receipt(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data = dict(reversed(list(trace_data.items())))
    assert _audit(trace_data, policy_data, evidence_data)["verdict"] == "pass"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda trace: trace["events"][4].__setitem__("seq", 40), "SEQUENCE_GAP"),
        (lambda trace: trace["events"][4].__setitem__("t_ns", 1), "TIME_REVERSED"),
        (lambda trace: trace["events"][4].__setitem__("phase", "ghost"), "PHASE_UNKNOWN"),
        (lambda trace: trace["events"][4].__setitem__("kind", "phase_enter"), "PHASE_NESTED"),
        (lambda trace: trace["events"][0].__setitem__("phase", "mate"), "INITIAL_PHASE_WRONG"),
        (lambda trace: trace["events"][2].__setitem__("phase", "mate"), "PHASE_EXIT_MISMATCH"),
        (lambda trace: trace["events"][4].__setitem__("phase", "approach"), "EVENT_PHASE_MISMATCH"),
    ],
)
def test_event_order_and_phase_violations(
    trace_data: dict[str, Any],
    policy_data: dict[str, Any],
    evidence_data: dict[str, Any],
    mutation: Any,
    code: str,
) -> None:
    mutation(trace_data)
    assert code in _codes(_audit(trace_data, policy_data, evidence_data))


def test_cross_phase_skip_reports_transition_and_precondition(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"] = [
        *trace_data["events"][:3],
        {"seq": 3, "t_ns": 300, "kind": "phase_enter", "phase": "verify"},
        {"seq": 4, "t_ns": 400, "kind": "checkpoint", "phase": "verify"},
        {"seq": 5, "t_ns": 500, "kind": "phase_exit", "phase": "verify"},
    ]
    codes = _codes(_audit(trace_data, policy_data, evidence_data))
    assert "TRANSITION_FORBIDDEN" in codes
    assert "PRECONDITION_MISSING" in codes


def test_reentered_phase_is_rejected(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"] = [
        *trace_data["events"][:3],
        {"seq": 3, "t_ns": 300, "kind": "phase_enter", "phase": "approach"},
    ]
    assert "PHASE_REENTERED" in _codes(_audit(trace_data, policy_data, evidence_data))


def test_exit_without_enter_is_rejected(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"] = [{"seq": 0, "t_ns": 0, "kind": "phase_exit", "phase": "approach"}]
    assert "PHASE_EXIT_WITHOUT_ENTER" in _codes(_audit(trace_data, policy_data, evidence_data))


def test_missing_required_kind_is_rejected(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    del trace_data["events"][4]
    for index, event in enumerate(trace_data["events"]):
        event["seq"] = index
    assert "REQUIRED_EVENT_MISSING" in _codes(_audit(trace_data, policy_data, evidence_data))


def test_unclosed_phase_and_terminal_incomplete(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"] = trace_data["events"][:5]
    codes = _codes(_audit(trace_data, policy_data, evidence_data))
    assert "PHASE_UNCLOSED" in codes
    assert "TERMINAL_PHASE_INCOMPLETE" in codes


def test_phase_duration_boundary_passes(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    policy_data["phases"][0]["max_duration_ns"] = 200
    assert _audit(trace_data, policy_data, evidence_data)["verdict"] == "pass"


def test_phase_duration_over_limit_fails(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    policy_data["phases"][0]["max_duration_ns"] = 199
    assert "PHASE_DURATION_EXCEEDED" in _codes(_audit(trace_data, policy_data, evidence_data))


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("contact_state", "slip", "CONTACT_STATE_FORBIDDEN"),
        ("force_n", [11, 0, 0], "FORCE_AXIS_EXCEEDED"),
        ("force_n", [10, 10, 10], "FORCE_NORM_EXCEEDED"),
        ("torque_nm", [2.1, 0, 0], "TORQUE_AXIS_EXCEEDED"),
        ("torque_nm", [2, 2, 2], "TORQUE_NORM_EXCEEDED"),
    ],
)
def test_contact_envelope_violations(
    trace_data: dict[str, Any],
    policy_data: dict[str, Any],
    evidence_data: dict[str, Any],
    field: str,
    value: object,
    code: str,
) -> None:
    trace_data["events"][5][field] = value
    assert code in _codes(_audit(trace_data, policy_data, evidence_data))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("force_n", [10, -10, 12]),
        ("torque_nm", [-2, 2, -2]),
    ],
)
def test_axis_threshold_is_inclusive(
    trace_data: dict[str, Any],
    policy_data: dict[str, Any],
    evidence_data: dict[str, Any],
    field: str,
    value: object,
) -> None:
    trace_data["events"][5][field] = value
    if field == "force_n":
        policy_data["phases"][1]["envelope"]["force_norm_max_n"] = 20
    else:
        policy_data["phases"][1]["envelope"]["torque_norm_max_nm"] = 4
    assert _audit(trace_data, policy_data, evidence_data)["verdict"] == "pass"


def test_norm_threshold_is_inclusive(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"][5]["force_n"] = [9, 12, 0]
    envelope = policy_data["phases"][1]["envelope"]
    envelope["force_abs_max_n"] = [20, 20, 20]
    envelope["force_norm_max_n"] = 15
    assert _audit(trace_data, policy_data, evidence_data)["verdict"] == "pass"


def test_contact_requires_state(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    del trace_data["events"][5]["contact_state"]
    assert "CONTACT_STATE_MISSING" in _codes(_audit(trace_data, policy_data, evidence_data))


@pytest.mark.parametrize(
    ("field", "code"), [("force_n", "FORCE_SAMPLE_MISSING"), ("torque_nm", "TORQUE_SAMPLE_MISSING")]
)
def test_contact_requires_wrench_samples(
    trace_data: dict[str, Any],
    policy_data: dict[str, Any],
    evidence_data: dict[str, Any],
    field: str,
    code: str,
) -> None:
    del trace_data["events"][5][field]
    assert code in _codes(_audit(trace_data, policy_data, evidence_data))


def test_contact_state_on_non_contact_event_is_rejected(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"][4]["contact_state"] = "stable"
    assert "CONTACT_STATE_UNEXPECTED" in _codes(_audit(trace_data, policy_data, evidence_data))


def test_unknown_evidence_reference_is_rejected(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"][4]["evidence_refs"] = ["unknown_item"]
    assert "EVIDENCE_REF_UNKNOWN" in _codes(_audit(trace_data, policy_data, evidence_data))


def test_wrong_environment_evidence_reference_is_rejected(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    evidence_data["items"].append(
        {
            "id": "hardware_only",
            "kind": "calibration",
            "sha256": "d" * 64,
            "applies_to": ["hardware"],
        }
    )
    trace_data["events"][4]["evidence_refs"] = ["hardware_only"]
    assert "EVIDENCE_REF_WRONG_ENVIRONMENT" in _codes(
        _audit(trace_data, policy_data, evidence_data)
    )


def test_missing_checklist_item_is_reported(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    evidence_data["items"] = [
        item for item in evidence_data["items"] if item["kind"] != "environment_snapshot"
    ]
    receipt = _audit(trace_data, policy_data, evidence_data)
    assert "EVIDENCE_REQUIREMENT_MISSING" in _codes(receipt)
    row = next(
        row for row in receipt["evidence_checklist"] if row["kind"] == "environment_snapshot"
    )
    assert row["satisfied"] is False


@pytest.mark.parametrize("source_format", ["rosbag2", "mcap"])
def test_recording_sources_require_artifact_digest(
    trace_data: dict[str, Any],
    policy_data: dict[str, Any],
    evidence_data: dict[str, Any],
    source_format: str,
) -> None:
    trace_data["source_format"] = source_format
    assert "SOURCE_DIGEST_MISSING" in _codes(_audit(trace_data, policy_data, evidence_data))


def test_recording_source_with_digest_passes(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["source_format"] = "mcap"
    trace_data["source_artifact_sha256"] = "e" * 64
    assert _audit(trace_data, policy_data, evidence_data)["verdict"] == "pass"


def test_failure_replay_identifies_minimal_prefix(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"][5]["force_n"] = [20, 0, 0]
    receipt = _audit(trace_data, policy_data, evidence_data)
    replay = receipt["failure_replay"]
    assert replay["first_code"] == "FORCE_AXIS_EXCEEDED"
    assert replay["end_index"] == 5
    assert replay["end_seq"] == 5
    assert len(replay["prefix_sha256"]) == 64


def test_failure_prefix_uses_event_position_when_sequence_is_wrong(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"][4]["seq"] = 40
    parsed = parse_trace(trace_data)
    receipt = audit(parsed, parse_policy(policy_data), parse_evidence(evidence_data))
    expected = canonical_sha256(
        {"run_id": parsed.run_id, "events": [event_as_dict(event) for event in parsed.events[:5]]}
    )
    assert receipt["failure_replay"] == {
        "first_code": "SEQUENCE_GAP",
        "end_index": 4,
        "end_seq": 40,
        "prefix_sha256": expected,
    }


def test_failure_replay_uses_earliest_event_not_check_order(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"][5]["force_n"] = [20, 0, 0]
    trace_data["events"][8]["seq"] = 80
    receipt = _audit(trace_data, policy_data, evidence_data)
    assert receipt["violations"][0]["code"] == "SEQUENCE_GAP"
    assert receipt["failure_replay"]["first_code"] == "FORCE_AXIS_EXCEEDED"
    assert receipt["failure_replay"]["end_index"] == 5
    assert receipt["failure_replay"]["end_seq"] == 5


def test_event_violation_carries_explicit_index(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"][5]["force_n"] = [20, 0, 0]
    violation = next(
        item
        for item in _audit(trace_data, policy_data, evidence_data)["violations"]
        if item["code"] == "FORCE_AXIS_EXCEEDED"
    )
    assert violation["event_index"] == 5


def test_non_event_failure_has_no_prefix(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    for event in trace_data["events"]:
        event.pop("evidence_refs", None)
    evidence_data["items"] = [
        item for item in evidence_data["items"] if item["kind"] != "environment_snapshot"
    ]
    receipt = _audit(trace_data, policy_data, evidence_data)
    assert receipt["failure_replay"] == {
        "first_code": "EVIDENCE_REQUIREMENT_MISSING",
        "end_index": None,
        "end_seq": None,
        "prefix_sha256": None,
    }


def test_phase_summary_is_policy_ordered(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    summaries = _audit(trace_data, policy_data, evidence_data)["phase_summary"]
    assert [item["phase"] for item in summaries] == ["approach", "mate", "verify"]
    assert summaries[0]["duration_ns"] == 200


def test_violation_output_is_bounded(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"] = [
        {"seq": index, "t_ns": index, "kind": "observation", "phase": "ghost"}
        for index in range(1001)
    ]
    receipt = _audit(trace_data, policy_data, evidence_data)
    assert receipt["counts"]["violations"] == 1000
    assert receipt["counts"]["violations_truncated"] is True


def test_truncation_preserves_earliest_event_for_failure_replay(
    trace_data: dict[str, Any], policy_data: dict[str, Any], evidence_data: dict[str, Any]
) -> None:
    trace_data["events"] = [
        {
            "seq": 0,
            "t_ns": 0,
            "kind": "phase_enter",
            "phase": "approach",
            "force_n": [999, 0, 0],
        },
        *[
            {
                "seq": index + 1,
                "t_ns": index,
                "kind": "observation",
                "phase": "approach",
            }
            for index in range(1, 1001)
        ],
    ]
    parsed = parse_trace(trace_data)
    receipt = audit(parsed, parse_policy(policy_data), parse_evidence(evidence_data))
    expected_prefix = canonical_sha256(
        {"run_id": parsed.run_id, "events": [event_as_dict(parsed.events[0])]}
    )

    assert receipt["counts"]["violations"] == 1000
    assert receipt["counts"]["violations_truncated"] is True
    assert receipt["failure_replay"] == {
        "first_code": "FORCE_AXIS_EXCEEDED",
        "end_index": 0,
        "end_seq": 0,
        "prefix_sha256": expected_prefix,
    }
    repeated = audit(parsed, parse_policy(policy_data), parse_evidence(evidence_data))
    assert canonical_bytes(receipt) == canonical_bytes(repeated)
