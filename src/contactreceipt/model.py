"""Strict data model for neutral civil-assembly traces and evidence."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, cast

from contactreceipt.errors import InputError, safe_label

SCHEMA_VERSION = "1.0"
MAX_EVENTS = 100_000
MAX_PHASES = 128
MAX_EVIDENCE_ITEMS = 2_048

EVENT_KINDS = frozenset(
    {"phase_enter", "phase_exit", "contact", "observation", "action", "checkpoint", "fault"}
)
CONTACT_STATES = frozenset({"none", "touch", "stable", "slip", "lost"})
ENVIRONMENTS = frozenset({"simulation", "hardware"})
SOURCE_FORMATS = frozenset({"neutral_json", "rosbag2", "mcap", "other"})
EVIDENCE_KINDS = frozenset(
    {
        "calibration",
        "controller_config",
        "dataset_provenance",
        "environment_snapshot",
        "replay_log",
        "robot_description",
        "safety_review",
        "sensor_sync",
        "software_bill",
    }
)
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Event:
    """One normalized observation in an assembly run."""

    seq: int
    t_ns: int
    kind: str
    phase: str
    contact_state: str | None
    force_n: Vec3 | None
    torque_nm: Vec3 | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Trace:
    """An ordered, simulator-neutral assembly trace."""

    run_id: str
    environment: str
    source_format: str
    source_artifact_sha256: str | None
    events: tuple[Event, ...]


@dataclass(frozen=True)
class Envelope:
    """Per-phase contact and wrench limits."""

    force_abs_max_n: Vec3 | None
    force_norm_max_n: float | None
    torque_abs_max_nm: Vec3 | None
    torque_norm_max_nm: float | None
    allowed_contact_states: frozenset[str]
    require_wrench_on_contact: bool


@dataclass(frozen=True)
class PhaseSpec:
    """Preconditions, transitions, expected events, and limits for one phase."""

    name: str
    requires: tuple[str, ...]
    allowed_next: tuple[str, ...]
    required_kinds: frozenset[str]
    max_duration_ns: int | None
    envelope: Envelope


@dataclass(frozen=True)
class EvidenceRequirement:
    """One sim-to-real evidence checklist row."""

    kind: str
    environments: frozenset[str]
    min_count: int


@dataclass(frozen=True)
class Policy:
    """Assembly contract used by the deterministic audit engine."""

    assembly_id: str
    initial_phase: str
    terminal_phase: str
    phases: tuple[PhaseSpec, ...]
    evidence_requirements: tuple[EvidenceRequirement, ...]


@dataclass(frozen=True)
class EvidenceItem:
    """Content-addressed evidence metadata; file contents are not read."""

    item_id: str
    kind: str
    sha256: str
    applies_to: frozenset[str]
    source_uri: str | None


@dataclass(frozen=True)
class EvidenceManifest:
    """Evidence inventory associated with a run."""

    items: tuple[EvidenceItem, ...]


def _fail(path: str, message: str) -> None:
    raise InputError(f"{path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    if not all(isinstance(key, str) for key in value):
        _fail(path, "object keys must be strings")
    return cast(dict[str, Any], value)


def _keys(value: dict[str, Any], *, required: set[str], optional: set[str], path: str) -> None:
    if any(any(0xD800 <= ord(character) <= 0xDFFF for character in key) for key in value):
        _fail(path, "object key contains a lone surrogate")
    missing = sorted(required - value.keys())
    if missing:
        _fail(path, f"missing field: {missing[0]}")
    unknown = sorted(value.keys() - required - optional)
    if unknown:
        _fail(path, f"unknown field: {safe_label(unknown[0])}")


def _string(value: Any, path: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str):
        _fail(path, "must be a string")
    if (
        not value
        or len(value) > max_len
        or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value)
    ):
        _fail(path, f"must contain 1..{max_len} printable characters")
    return cast(str, value)


def _identifier(value: Any, path: str) -> str:
    text = _string(value, path, max_len=64)
    if not ID_RE.fullmatch(text):
        _fail(path, "must match ^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
    return text


def _sha256(value: Any, path: str) -> str:
    text = _string(value, path, max_len=64)
    if not SHA256_RE.fullmatch(text):
        _fail(path, "must be 64 lowercase hexadecimal characters")
    return text


def _integer(value: Any, path: str, *, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "must be an integer")
    if not minimum <= value <= maximum:
        _fail(path, f"must be between {minimum} and {maximum}")
    return cast(int, value)


def _number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        _fail(path, "must be a finite number")
    if positive and result <= 0:
        _fail(path, "must be greater than zero")
    if abs(result) > 1_000_000_000:
        _fail(path, "absolute value exceeds 1000000000")
    return result


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "must be a boolean")
    return cast(bool, value)


def _array(value: Any, path: str, *, max_items: int) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    if len(value) > max_items:
        _fail(path, f"must contain at most {max_items} items")
    return cast(list[Any], value)


def _enum(value: Any, path: str, allowed: frozenset[str]) -> str:
    text = _string(value, path, max_len=64)
    if text not in allowed:
        _fail(path, f"must be one of: {', '.join(sorted(allowed))}")
    return text


def _vec3(value: Any, path: str, *, positive: bool = False) -> Vec3:
    items = _array(value, path, max_items=3)
    if len(items) != 3:
        _fail(path, "must contain exactly 3 numbers")
    return (
        _number(items[0], f"{path}/0", positive=positive),
        _number(items[1], f"{path}/1", positive=positive),
        _number(items[2], f"{path}/2", positive=positive),
    )


def _id_array(value: Any, path: str, *, max_items: int = 128) -> tuple[str, ...]:
    items = _array(value, path, max_items=max_items)
    result = tuple(_identifier(item, f"{path}/{index}") for index, item in enumerate(items))
    if len(set(result)) != len(result):
        _fail(path, "must not contain duplicates")
    return result


def _version(root: dict[str, Any], path: str) -> None:
    if root.get("schema_version") != SCHEMA_VERSION:
        _fail(f"{path}/schema_version", f"must equal {SCHEMA_VERSION}")


def _parse_event(value: Any, index: int) -> Event:
    path = f"/events/{index}"
    item = _object(value, path)
    _keys(
        item,
        required={"seq", "t_ns", "kind", "phase"},
        optional={"contact_state", "force_n", "torque_nm", "evidence_refs"},
        path=path,
    )
    return Event(
        seq=_integer(item["seq"], f"{path}/seq", maximum=MAX_EVENTS - 1),
        t_ns=_integer(item["t_ns"], f"{path}/t_ns"),
        kind=_enum(item["kind"], f"{path}/kind", EVENT_KINDS),
        phase=_identifier(item["phase"], f"{path}/phase"),
        contact_state=(
            _enum(item["contact_state"], f"{path}/contact_state", CONTACT_STATES)
            if "contact_state" in item
            else None
        ),
        force_n=_vec3(item["force_n"], f"{path}/force_n") if "force_n" in item else None,
        torque_nm=(_vec3(item["torque_nm"], f"{path}/torque_nm") if "torque_nm" in item else None),
        evidence_refs=(
            _id_array(item["evidence_refs"], f"{path}/evidence_refs", max_items=64)
            if "evidence_refs" in item
            else ()
        ),
    )


def parse_trace(value: Any) -> Trace:
    """Parse and strictly validate a trace object's shape and scalar values."""
    root = _object(value, "/")
    _keys(
        root,
        required={"schema_version", "run_id", "environment", "source_format", "events"},
        optional={"source_artifact_sha256"},
        path="/",
    )
    _version(root, "")
    events = _array(root["events"], "/events", max_items=MAX_EVENTS)
    if not events:
        _fail("/events", "must contain at least one event")
    return Trace(
        run_id=_identifier(root["run_id"], "/run_id"),
        environment=_enum(root["environment"], "/environment", ENVIRONMENTS),
        source_format=_enum(root["source_format"], "/source_format", SOURCE_FORMATS),
        source_artifact_sha256=(
            _sha256(root["source_artifact_sha256"], "/source_artifact_sha256")
            if "source_artifact_sha256" in root
            else None
        ),
        events=tuple(_parse_event(item, index) for index, item in enumerate(events)),
    )


def _parse_envelope(value: Any, path: str) -> Envelope:
    item = _object(value, path)
    _keys(
        item,
        required={"allowed_contact_states", "require_wrench_on_contact"},
        optional={
            "force_abs_max_n",
            "force_norm_max_n",
            "torque_abs_max_nm",
            "torque_norm_max_nm",
        },
        path=path,
    )
    states_raw = _array(
        item["allowed_contact_states"], f"{path}/allowed_contact_states", max_items=5
    )
    states = frozenset(
        _enum(state, f"{path}/allowed_contact_states/{index}", CONTACT_STATES)
        for index, state in enumerate(states_raw)
    )
    if len(states) != len(states_raw):
        _fail(f"{path}/allowed_contact_states", "must not contain duplicates")
    if not states:
        _fail(f"{path}/allowed_contact_states", "must contain at least one state")
    return Envelope(
        force_abs_max_n=(
            _vec3(item["force_abs_max_n"], f"{path}/force_abs_max_n", positive=True)
            if "force_abs_max_n" in item
            else None
        ),
        force_norm_max_n=(
            _number(item["force_norm_max_n"], f"{path}/force_norm_max_n", positive=True)
            if "force_norm_max_n" in item
            else None
        ),
        torque_abs_max_nm=(
            _vec3(item["torque_abs_max_nm"], f"{path}/torque_abs_max_nm", positive=True)
            if "torque_abs_max_nm" in item
            else None
        ),
        torque_norm_max_nm=(
            _number(item["torque_norm_max_nm"], f"{path}/torque_norm_max_nm", positive=True)
            if "torque_norm_max_nm" in item
            else None
        ),
        allowed_contact_states=states,
        require_wrench_on_contact=_bool(
            item["require_wrench_on_contact"], f"{path}/require_wrench_on_contact"
        ),
    )


def _parse_phase(value: Any, index: int) -> PhaseSpec:
    path = f"/phases/{index}"
    item = _object(value, path)
    _keys(
        item,
        required={"name", "requires", "allowed_next", "required_kinds", "envelope"},
        optional={"max_duration_ns"},
        path=path,
    )
    kinds_raw = _array(item["required_kinds"], f"{path}/required_kinds", max_items=7)
    kinds = frozenset(
        _enum(kind, f"{path}/required_kinds/{position}", EVENT_KINDS)
        for position, kind in enumerate(kinds_raw)
    )
    if len(kinds) != len(kinds_raw):
        _fail(f"{path}/required_kinds", "must not contain duplicates")
    return PhaseSpec(
        name=_identifier(item["name"], f"{path}/name"),
        requires=_id_array(item["requires"], f"{path}/requires"),
        allowed_next=_id_array(item["allowed_next"], f"{path}/allowed_next"),
        required_kinds=kinds,
        max_duration_ns=(
            _integer(item["max_duration_ns"], f"{path}/max_duration_ns", minimum=1)
            if "max_duration_ns" in item
            else None
        ),
        envelope=_parse_envelope(item["envelope"], f"{path}/envelope"),
    )


def _parse_requirement(value: Any, index: int) -> EvidenceRequirement:
    path = f"/evidence_requirements/{index}"
    item = _object(value, path)
    _keys(item, required={"kind", "environments", "min_count"}, optional=set(), path=path)
    environments_raw = _array(item["environments"], f"{path}/environments", max_items=2)
    environments = frozenset(
        _enum(environment, f"{path}/environments/{position}", ENVIRONMENTS)
        for position, environment in enumerate(environments_raw)
    )
    if not environments:
        _fail(f"{path}/environments", "must contain at least one environment")
    if len(environments) != len(environments_raw):
        _fail(f"{path}/environments", "must not contain duplicates")
    return EvidenceRequirement(
        kind=_enum(item["kind"], f"{path}/kind", EVIDENCE_KINDS),
        environments=environments,
        min_count=_integer(item["min_count"], f"{path}/min_count", minimum=1, maximum=100),
    )


def _check_policy_graph(policy: Policy) -> None:
    names = [phase.name for phase in policy.phases]
    if len(set(names)) != len(names):
        _fail("/phases", "phase names must be unique")
    known = set(names)
    if policy.initial_phase not in known:
        _fail("/initial_phase", "must name a declared phase")
    if policy.terminal_phase not in known:
        _fail("/terminal_phase", "must name a declared phase")
    for index, phase in enumerate(policy.phases):
        for relation, targets in (
            ("requires", phase.requires),
            ("allowed_next", phase.allowed_next),
        ):
            for target in targets:
                if target not in known:
                    _fail(f"/phases/{index}/{relation}", f"unknown phase: {target}")
                if target == phase.name:
                    _fail(f"/phases/{index}/{relation}", "self-reference is not allowed")

    dependencies = {phase.name: phase.requires for phase in policy.phases}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            _fail("/phases", "prerequisite graph must be acyclic")
        if name in visited:
            return
        visiting.add(name)
        for dependency in dependencies[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in names:
        visit(name)

    initial = next(phase for phase in policy.phases if phase.name == policy.initial_phase)
    if initial.requires:
        _fail("/initial_phase", "initial phase cannot have prerequisites")
    terminal = next(phase for phase in policy.phases if phase.name == policy.terminal_phase)
    if terminal.allowed_next:
        _fail("/terminal_phase", "terminal phase cannot allow a next phase")

    reachable = {policy.initial_phase}
    pending = [policy.initial_phase]
    phase_map = {phase.name: phase for phase in policy.phases}
    while pending:
        current = pending.pop()
        for target in phase_map[current].allowed_next:
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    if policy.terminal_phase not in reachable:
        _fail("/terminal_phase", "must be reachable from initial_phase through allowed_next")


def parse_policy(value: Any) -> Policy:
    """Parse an assembly policy and validate all phase graph references."""
    root = _object(value, "/")
    _keys(
        root,
        required={
            "schema_version",
            "assembly_id",
            "initial_phase",
            "terminal_phase",
            "phases",
            "evidence_requirements",
        },
        optional=set(),
        path="/",
    )
    _version(root, "")
    phases_raw = _array(root["phases"], "/phases", max_items=MAX_PHASES)
    if not phases_raw:
        _fail("/phases", "must contain at least one phase")
    requirements_raw = _array(
        root["evidence_requirements"],
        "/evidence_requirements",
        max_items=len(EVIDENCE_KINDS) * (2 ** len(ENVIRONMENTS) - 1),
    )
    policy = Policy(
        assembly_id=_identifier(root["assembly_id"], "/assembly_id"),
        initial_phase=_identifier(root["initial_phase"], "/initial_phase"),
        terminal_phase=_identifier(root["terminal_phase"], "/terminal_phase"),
        phases=tuple(_parse_phase(item, index) for index, item in enumerate(phases_raw)),
        evidence_requirements=tuple(
            _parse_requirement(item, index) for index, item in enumerate(requirements_raw)
        ),
    )
    requirement_keys = [
        (requirement.kind, tuple(sorted(requirement.environments)))
        for requirement in policy.evidence_requirements
    ]
    if len(set(requirement_keys)) != len(requirement_keys):
        _fail("/evidence_requirements", "requirements must be unique by kind and environments")
    _check_policy_graph(policy)
    return policy


def _parse_evidence_item(value: Any, index: int) -> EvidenceItem:
    path = f"/items/{index}"
    item = _object(value, path)
    _keys(
        item,
        required={"id", "kind", "sha256", "applies_to"},
        optional={"source_uri"},
        path=path,
    )
    applies_raw = _array(item["applies_to"], f"{path}/applies_to", max_items=2)
    applies = frozenset(
        _enum(environment, f"{path}/applies_to/{position}", ENVIRONMENTS)
        for position, environment in enumerate(applies_raw)
    )
    if not applies:
        _fail(f"{path}/applies_to", "must contain at least one environment")
    if len(applies) != len(applies_raw):
        _fail(f"{path}/applies_to", "must not contain duplicates")
    return EvidenceItem(
        item_id=_identifier(item["id"], f"{path}/id"),
        kind=_enum(item["kind"], f"{path}/kind", EVIDENCE_KINDS),
        sha256=_sha256(item["sha256"], f"{path}/sha256"),
        applies_to=applies,
        source_uri=(
            _string(item["source_uri"], f"{path}/source_uri") if "source_uri" in item else None
        ),
    )


def parse_evidence(value: Any) -> EvidenceManifest:
    """Parse the content-addressed sim-to-real evidence manifest."""
    root = _object(value, "/")
    _keys(root, required={"schema_version", "items"}, optional=set(), path="/")
    _version(root, "")
    items_raw = _array(root["items"], "/items", max_items=MAX_EVIDENCE_ITEMS)
    items = tuple(_parse_evidence_item(item, index) for index, item in enumerate(items_raw))
    if len({item.item_id for item in items}) != len(items):
        _fail("/items", "evidence ids must be unique")
    return EvidenceManifest(items=items)


def event_as_dict(event: Event) -> dict[str, Any]:
    """Return the normalized JSON representation used for fingerprints."""
    result: dict[str, Any] = {
        "seq": event.seq,
        "t_ns": event.t_ns,
        "kind": event.kind,
        "phase": event.phase,
    }
    if event.contact_state is not None:
        result["contact_state"] = event.contact_state
    if event.force_n is not None:
        result["force_n"] = list(event.force_n)
    if event.torque_nm is not None:
        result["torque_nm"] = list(event.torque_nm)
    if event.evidence_refs:
        result["evidence_refs"] = list(event.evidence_refs)
    return result


def trace_as_dict(trace: Trace) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": trace.run_id,
        "environment": trace.environment,
        "source_format": trace.source_format,
        "events": [event_as_dict(event) for event in trace.events],
    }
    if trace.source_artifact_sha256 is not None:
        result["source_artifact_sha256"] = trace.source_artifact_sha256
    return result


def policy_as_dict(policy: Policy) -> dict[str, Any]:
    phases: list[dict[str, Any]] = []
    for phase in policy.phases:
        envelope: dict[str, Any] = {
            "allowed_contact_states": sorted(phase.envelope.allowed_contact_states),
            "require_wrench_on_contact": phase.envelope.require_wrench_on_contact,
        }
        for key, item in (
            ("force_abs_max_n", phase.envelope.force_abs_max_n),
            ("force_norm_max_n", phase.envelope.force_norm_max_n),
            ("torque_abs_max_nm", phase.envelope.torque_abs_max_nm),
            ("torque_norm_max_nm", phase.envelope.torque_norm_max_nm),
        ):
            if item is not None:
                envelope[key] = list(item) if isinstance(item, tuple) else item
        phase_value: dict[str, Any] = {
            "name": phase.name,
            "requires": list(phase.requires),
            "allowed_next": list(phase.allowed_next),
            "required_kinds": sorted(phase.required_kinds),
            "envelope": envelope,
        }
        if phase.max_duration_ns is not None:
            phase_value["max_duration_ns"] = phase.max_duration_ns
        phases.append(phase_value)
    return {
        "schema_version": SCHEMA_VERSION,
        "assembly_id": policy.assembly_id,
        "initial_phase": policy.initial_phase,
        "terminal_phase": policy.terminal_phase,
        "phases": phases,
        "evidence_requirements": [
            {
                "kind": requirement.kind,
                "environments": sorted(requirement.environments),
                "min_count": requirement.min_count,
            }
            for requirement in policy.evidence_requirements
        ],
    }


def evidence_as_dict(manifest: EvidenceManifest) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in manifest.items:
        value: dict[str, Any] = {
            "id": item.item_id,
            "kind": item.kind,
            "sha256": item.sha256,
            "applies_to": sorted(item.applies_to),
        }
        if item.source_uri is not None:
            value["source_uri"] = item.source_uri
        items.append(value)
    return {"schema_version": SCHEMA_VERSION, "items": items}
