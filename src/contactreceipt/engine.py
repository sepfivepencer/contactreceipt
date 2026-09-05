"""Deterministic civil-assembly trace audit engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from contactreceipt.canonical import canonical_sha256
from contactreceipt.model import (
    Event,
    EvidenceManifest,
    PhaseSpec,
    Policy,
    Trace,
    event_as_dict,
    evidence_as_dict,
    policy_as_dict,
    trace_as_dict,
)

TOOL_VERSION = "0.1.1"
ALGORITHM = "civil-assembly-v1"
MAX_VIOLATIONS = 1_000


@dataclass(frozen=True)
class _Violation:
    code: str
    path: str
    message: str
    event_index: int | None = None
    event_seq: int | None = None
    phase: str | None = None
    severity: str = "error"

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }
        if self.event_index is not None:
            result["event_index"] = self.event_index
        if self.event_seq is not None:
            result["event_seq"] = self.event_seq
        if self.phase is not None:
            result["phase"] = self.phase
        return result


def _display(value: float) -> str:
    return format(value, ".9g")


def _norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


class _Audit:
    def __init__(self, trace: Trace, policy: Policy, evidence: EvidenceManifest) -> None:
        self.trace = trace
        self.policy = policy
        self.evidence = evidence
        self.phase_by_name = {phase.name: phase for phase in policy.phases}
        self.evidence_by_id = {item.item_id: item for item in evidence.items}
        self.violations: list[_Violation] = []
        self.completed: set[str] = set()
        self.entered: set[str] = set()
        self.start_times: dict[str, int] = {}
        self.end_times: dict[str, int] = {}
        self.seen_kinds: dict[str, set[str]] = {phase.name: set() for phase in policy.phases}
        self.active: str | None = None
        self.last_completed: str | None = None
        self.event_index_by_identity = {
            id(event): index for index, event in enumerate(self.trace.events)
        }
        self.earliest_event_violation: _Violation | None = None
        self.violations_truncated = False

    def add(
        self,
        code: str,
        path: str,
        message: str,
        *,
        event: Event | None = None,
        phase: str | None = None,
    ) -> None:
        violation = _Violation(
            code=code,
            path=path,
            message=message,
            event_index=(self.event_index_by_identity[id(event)] if event is not None else None),
            event_seq=event.seq if event is not None else None,
            phase=phase if phase is not None else (event.phase if event is not None else None),
        )
        if violation.event_index is not None and (
            self.earliest_event_violation is None
            or self.earliest_event_violation.event_index is None
            or violation.event_index < self.earliest_event_violation.event_index
        ):
            self.earliest_event_violation = violation
        if len(self.violations) >= MAX_VIOLATIONS:
            self.violations_truncated = True
            return
        self.violations.append(violation)

    def check_sequence(self) -> None:
        previous_time: int | None = None
        for index, event in enumerate(self.trace.events):
            if event.seq != index:
                self.add(
                    "SEQUENCE_GAP",
                    f"/events/{index}/seq",
                    f"expected sequence {index}, observed {event.seq}",
                    event=event,
                )
            if previous_time is not None and event.t_ns < previous_time:
                self.add(
                    "TIME_REVERSED",
                    f"/events/{index}/t_ns",
                    "timestamp precedes the previous event",
                    event=event,
                )
            previous_time = event.t_ns

    def check_source(self) -> None:
        if (
            self.trace.source_format in {"rosbag2", "mcap"}
            and not self.trace.source_artifact_sha256
        ):
            self.add(
                "SOURCE_DIGEST_MISSING",
                "/source_artifact_sha256",
                f"{self.trace.source_format} sources require a content digest",
            )

    def _enter(self, event: Event, index: int, spec: PhaseSpec) -> None:
        if self.active is not None:
            self.add(
                "PHASE_NESTED",
                f"/events/{index}",
                f"cannot enter {event.phase} while {self.active} is active",
                event=event,
            )
            return
        if event.phase in self.entered:
            self.add(
                "PHASE_REENTERED",
                f"/events/{index}/phase",
                "a phase may be entered only once",
                event=event,
            )
            return
        if not self.entered and event.phase != self.policy.initial_phase:
            self.add(
                "INITIAL_PHASE_WRONG",
                f"/events/{index}/phase",
                f"first phase must be {self.policy.initial_phase}",
                event=event,
            )
        if self.last_completed is not None:
            previous = self.phase_by_name[self.last_completed]
            if event.phase not in previous.allowed_next:
                self.add(
                    "TRANSITION_FORBIDDEN",
                    f"/events/{index}/phase",
                    f"{self.last_completed} does not allow transition to {event.phase}",
                    event=event,
                )
        missing = sorted(set(spec.requires) - self.completed)
        if missing:
            self.add(
                "PRECONDITION_MISSING",
                f"/events/{index}/phase",
                f"required phase not completed: {missing[0]}",
                event=event,
            )
        self.active = event.phase
        self.entered.add(event.phase)
        self.start_times[event.phase] = event.t_ns

    def _exit(self, event: Event, index: int, spec: PhaseSpec) -> None:
        if self.active is None:
            self.add(
                "PHASE_EXIT_WITHOUT_ENTER",
                f"/events/{index}",
                "phase_exit has no active phase",
                event=event,
            )
            return
        if event.phase != self.active:
            self.add(
                "PHASE_EXIT_MISMATCH",
                f"/events/{index}/phase",
                f"active phase is {self.active}",
                event=event,
            )
            return
        missing = sorted(spec.required_kinds - self.seen_kinds[event.phase])
        if missing:
            self.add(
                "REQUIRED_EVENT_MISSING",
                f"/events/{index}",
                f"phase lacks required event kind: {missing[0]}",
                event=event,
            )
        duration = event.t_ns - self.start_times[event.phase]
        if spec.max_duration_ns is not None and duration > spec.max_duration_ns:
            self.add(
                "PHASE_DURATION_EXCEEDED",
                f"/events/{index}/t_ns",
                f"duration {duration} ns exceeds {spec.max_duration_ns} ns",
                event=event,
            )
        self.end_times[event.phase] = event.t_ns
        self.completed.add(event.phase)
        self.last_completed = event.phase
        self.active = None

    def _check_vector(
        self,
        *,
        vector: tuple[float, float, float] | None,
        absolute_limit: tuple[float, float, float] | None,
        norm_limit: float | None,
        index: int,
        event: Event,
        field: str,
        unit: str,
        absolute_code: str,
        norm_code: str,
    ) -> None:
        if vector is None:
            return
        if absolute_limit is not None:
            for axis, (observed, limit) in enumerate(zip(vector, absolute_limit, strict=True)):
                if abs(observed) > limit:
                    self.add(
                        absolute_code,
                        f"/events/{index}/{field}/{axis}",
                        (
                            f"absolute value {_display(abs(observed))} {unit} "
                            f"exceeds {_display(limit)} {unit}"
                        ),
                        event=event,
                    )
        if norm_limit is not None:
            observed_norm = _norm(vector)
            if observed_norm > norm_limit:
                self.add(
                    norm_code,
                    f"/events/{index}/{field}",
                    f"norm {_display(observed_norm)} {unit} exceeds {_display(norm_limit)} {unit}",
                    event=event,
                )

    def _check_event_safety(self, event: Event, index: int, spec: PhaseSpec) -> None:
        envelope = spec.envelope
        if event.kind == "contact" and event.contact_state is None:
            self.add(
                "CONTACT_STATE_MISSING",
                f"/events/{index}/contact_state",
                "contact events require a contact_state",
                event=event,
            )
        if event.kind != "contact" and event.contact_state is not None:
            self.add(
                "CONTACT_STATE_UNEXPECTED",
                f"/events/{index}/contact_state",
                "contact_state is only valid on contact events",
                event=event,
            )
        if (
            event.contact_state is not None
            and event.contact_state not in envelope.allowed_contact_states
        ):
            self.add(
                "CONTACT_STATE_FORBIDDEN",
                f"/events/{index}/contact_state",
                f"state {event.contact_state} is outside the phase envelope",
                event=event,
            )
        if (
            envelope.require_wrench_on_contact
            and event.kind == "contact"
            and event.contact_state in {"touch", "stable", "slip"}
        ):
            if event.force_n is None:
                self.add(
                    "FORCE_SAMPLE_MISSING",
                    f"/events/{index}/force_n",
                    "contact event requires a force sample",
                    event=event,
                )
            if event.torque_nm is None:
                self.add(
                    "TORQUE_SAMPLE_MISSING",
                    f"/events/{index}/torque_nm",
                    "contact event requires a torque sample",
                    event=event,
                )
        self._check_vector(
            vector=event.force_n,
            absolute_limit=envelope.force_abs_max_n,
            norm_limit=envelope.force_norm_max_n,
            index=index,
            event=event,
            field="force_n",
            unit="N",
            absolute_code="FORCE_AXIS_EXCEEDED",
            norm_code="FORCE_NORM_EXCEEDED",
        )
        self._check_vector(
            vector=event.torque_nm,
            absolute_limit=envelope.torque_abs_max_nm,
            norm_limit=envelope.torque_norm_max_nm,
            index=index,
            event=event,
            field="torque_nm",
            unit="N.m",
            absolute_code="TORQUE_AXIS_EXCEEDED",
            norm_code="TORQUE_NORM_EXCEEDED",
        )

    def _check_references(self, event: Event, index: int) -> None:
        for position, reference in enumerate(event.evidence_refs):
            item = self.evidence_by_id.get(reference)
            if item is None:
                self.add(
                    "EVIDENCE_REF_UNKNOWN",
                    f"/events/{index}/evidence_refs/{position}",
                    f"unknown evidence id: {reference}",
                    event=event,
                )
            elif self.trace.environment not in item.applies_to:
                self.add(
                    "EVIDENCE_REF_WRONG_ENVIRONMENT",
                    f"/events/{index}/evidence_refs/{position}",
                    f"evidence {reference} does not apply to {self.trace.environment}",
                    event=event,
                )

    def check_events(self) -> None:
        for index, event in enumerate(self.trace.events):
            spec = self.phase_by_name.get(event.phase)
            if spec is None:
                self.add(
                    "PHASE_UNKNOWN",
                    f"/events/{index}/phase",
                    f"unknown policy phase: {event.phase}",
                    event=event,
                )
                self._check_references(event, index)
                continue
            if event.kind == "phase_enter":
                self._enter(event, index, spec)
            elif self.active is None:
                self.add(
                    "EVENT_OUTSIDE_PHASE",
                    f"/events/{index}",
                    "event occurred with no active phase",
                    event=event,
                )
            elif event.phase != self.active:
                self.add(
                    "EVENT_PHASE_MISMATCH",
                    f"/events/{index}/phase",
                    f"active phase is {self.active}",
                    event=event,
                )

            if self.active == event.phase:
                self.seen_kinds[event.phase].add(event.kind)
            self._check_event_safety(event, index, spec)
            self._check_references(event, index)
            if event.kind == "phase_exit":
                self._exit(event, index, spec)

        if self.active is not None:
            self.add(
                "PHASE_UNCLOSED",
                "/events",
                f"trace ended while {self.active} was active",
                phase=self.active,
            )
        if self.policy.terminal_phase not in self.completed:
            self.add(
                "TERMINAL_PHASE_INCOMPLETE",
                "/events",
                f"terminal phase {self.policy.terminal_phase} was not completed",
                phase=self.policy.terminal_phase,
            )

    def evidence_checklist(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, requirement in enumerate(self.policy.evidence_requirements):
            if self.trace.environment not in requirement.environments:
                continue
            matches = sorted(
                item.item_id
                for item in self.evidence.items
                if item.kind == requirement.kind and self.trace.environment in item.applies_to
            )
            satisfied = len(matches) >= requirement.min_count
            rows.append(
                {
                    "kind": requirement.kind,
                    "environment": self.trace.environment,
                    "min_count": requirement.min_count,
                    "matched_ids": matches,
                    "satisfied": satisfied,
                }
            )
            if not satisfied:
                self.add(
                    "EVIDENCE_REQUIREMENT_MISSING",
                    f"/evidence_requirements/{index}",
                    (
                        f"requires {requirement.min_count} {requirement.kind} item(s), "
                        f"found {len(matches)}"
                    ),
                )
        return rows

    def phase_summary(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for phase in self.policy.phases:
            if phase.name in self.completed:
                start = self.start_times[phase.name]
                end = self.end_times[phase.name]
                summaries.append(
                    {
                        "phase": phase.name,
                        "status": "completed",
                        "start_ns": start,
                        "end_ns": end,
                        "duration_ns": end - start,
                    }
                )
            elif phase.name == self.active:
                summaries.append(
                    {
                        "phase": phase.name,
                        "status": "active",
                        "start_ns": self.start_times[phase.name],
                    }
                )
            elif phase.name in self.entered:
                summaries.append({"phase": phase.name, "status": "entered_invalid"})
            else:
                summaries.append({"phase": phase.name, "status": "not_started"})
        return summaries

    def failure_replay(self) -> dict[str, Any] | None:
        errors = [violation for violation in self.violations if violation.severity == "error"]
        first = self.earliest_event_violation
        if first is None:
            first = next(iter(errors), None)
        if first is None:
            return None
        if first.event_index is None or first.event_seq is None:
            return {
                "first_code": first.code,
                "end_index": None,
                "end_seq": None,
                "prefix_sha256": None,
            }
        if not 0 <= first.event_index < len(self.trace.events):
            return {
                "first_code": first.code,
                "end_index": None,
                "end_seq": None,
                "prefix_sha256": None,
            }
        prefix = {
            "run_id": self.trace.run_id,
            "events": [
                event_as_dict(event) for event in self.trace.events[: first.event_index + 1]
            ],
        }
        return {
            "first_code": first.code,
            "end_index": first.event_index,
            "end_seq": first.event_seq,
            "prefix_sha256": canonical_sha256(prefix),
        }

    def run(self) -> dict[str, Any]:
        self.check_sequence()
        self.check_source()
        self.check_events()
        checklist = self.evidence_checklist()
        summaries = self.phase_summary()
        violations = [violation.as_dict() for violation in self.violations]
        receipt: dict[str, Any] = {
            "schema_version": "1.0",
            "receipt_type": "contactreceipt.audit",
            "tool": {
                "name": "contactreceipt",
                "version": TOOL_VERSION,
                "algorithm": ALGORITHM,
            },
            "subject": {
                "run_id": self.trace.run_id,
                "assembly_id": self.policy.assembly_id,
                "environment": self.trace.environment,
                "source_format": self.trace.source_format,
            },
            "input_fingerprints": {
                "trace_sha256": canonical_sha256(trace_as_dict(self.trace)),
                "policy_sha256": canonical_sha256(policy_as_dict(self.policy)),
                "evidence_sha256": canonical_sha256(evidence_as_dict(self.evidence)),
            },
            "verdict": "pass" if not violations else "fail",
            "counts": {
                "events": len(self.trace.events),
                "phases_completed": len(self.completed),
                "violations": len(violations),
                "violations_truncated": self.violations_truncated,
            },
            "phase_summary": summaries,
            "evidence_checklist": checklist,
            "violations": violations,
            "failure_replay": self.failure_replay(),
        }
        receipt["receipt_id"] = f"sha256:{canonical_sha256(receipt)}"
        return receipt


def audit(trace: Trace, policy: Policy, evidence: EvidenceManifest) -> dict[str, Any]:
    """Return a deterministic content-addressed validation receipt."""
    return _Audit(trace, policy, evidence).run()
