"""JSON Schema documents for interchange and editor support."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from contactreceipt.errors import safe_label
from contactreceipt.model import (
    CONTACT_STATES,
    ENVIRONMENTS,
    EVENT_KINDS,
    EVIDENCE_KINDS,
    SOURCE_FORMATS,
)

VIOLATION_CODES = sorted(
    {
        "CONTACT_STATE_FORBIDDEN",
        "CONTACT_STATE_MISSING",
        "CONTACT_STATE_UNEXPECTED",
        "EVENT_OUTSIDE_PHASE",
        "EVENT_PHASE_MISMATCH",
        "EVIDENCE_REF_UNKNOWN",
        "EVIDENCE_REF_WRONG_ENVIRONMENT",
        "EVIDENCE_REQUIREMENT_MISSING",
        "FORCE_AXIS_EXCEEDED",
        "FORCE_NORM_EXCEEDED",
        "FORCE_SAMPLE_MISSING",
        "INITIAL_PHASE_WRONG",
        "PHASE_DURATION_EXCEEDED",
        "PHASE_EXIT_MISMATCH",
        "PHASE_EXIT_WITHOUT_ENTER",
        "PHASE_NESTED",
        "PHASE_REENTERED",
        "PHASE_UNCLOSED",
        "PHASE_UNKNOWN",
        "PRECONDITION_MISSING",
        "REQUIRED_EVENT_MISSING",
        "SEQUENCE_GAP",
        "SOURCE_DIGEST_MISSING",
        "TERMINAL_PHASE_INCOMPLETE",
        "TIME_REVERSED",
        "TORQUE_AXIS_EXCEEDED",
        "TORQUE_NORM_EXCEEDED",
        "TORQUE_SAMPLE_MISSING",
        "TRANSITION_FORBIDDEN",
    }
)

SCHEMA_BASE = "https://github.com/sepfivepencer/contactreceipt/schema/"

IDENTIFIER: dict[str, Any] = {
    "type": "string",
    "pattern": "^[A-Za-z][A-Za-z0-9_.:-]{0,63}$",
}
SHA256: dict[str, Any] = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
VEC3: dict[str, Any] = {
    "type": "array",
    "prefixItems": [
        {"type": "number", "minimum": -1000000000, "maximum": 1000000000},
        {"type": "number", "minimum": -1000000000, "maximum": 1000000000},
        {"type": "number", "minimum": -1000000000, "maximum": 1000000000},
    ],
    "items": False,
    "minItems": 3,
    "maxItems": 3,
}
POSITIVE_VEC3: dict[str, Any] = {
    "type": "array",
    "prefixItems": [
        {"type": "number", "exclusiveMinimum": 0, "maximum": 1000000000},
        {"type": "number", "exclusiveMinimum": 0, "maximum": 1000000000},
        {"type": "number", "exclusiveMinimum": 0, "maximum": 1000000000},
    ],
    "items": False,
    "minItems": 3,
    "maxItems": 3,
}


def _root(name: str) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_BASE}{name}.schema.json",
        "title": f"ContactReceipt {name}",
        "type": "object",
        "additionalProperties": False,
    }


def _trace_schema() -> dict[str, Any]:
    schema = _root("trace")
    schema.update(
        {
            "required": ["schema_version", "run_id", "environment", "source_format", "events"],
            "properties": {
                "schema_version": {"const": "1.0"},
                "run_id": IDENTIFIER,
                "environment": {"enum": sorted(ENVIRONMENTS)},
                "source_format": {"enum": sorted(SOURCE_FORMATS)},
                "source_artifact_sha256": SHA256,
                "events": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100000,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["seq", "t_ns", "kind", "phase"],
                        "properties": {
                            "seq": {"type": "integer", "minimum": 0, "maximum": 99999},
                            "t_ns": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 9223372036854775807,
                            },
                            "kind": {"enum": sorted(EVENT_KINDS)},
                            "phase": IDENTIFIER,
                            "contact_state": {"enum": sorted(CONTACT_STATES)},
                            "force_n": deepcopy(VEC3),
                            "torque_nm": deepcopy(VEC3),
                            "evidence_refs": {
                                "type": "array",
                                "maxItems": 64,
                                "uniqueItems": True,
                                "items": IDENTIFIER,
                            },
                        },
                    },
                },
            },
        }
    )
    return schema


def _policy_schema() -> dict[str, Any]:
    schema = _root("policy")
    schema.update(
        {
            "required": [
                "schema_version",
                "assembly_id",
                "initial_phase",
                "terminal_phase",
                "phases",
                "evidence_requirements",
            ],
            "properties": {
                "schema_version": {"const": "1.0"},
                "assembly_id": IDENTIFIER,
                "initial_phase": IDENTIFIER,
                "terminal_phase": IDENTIFIER,
                "phases": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 128,
                    "items": {"$ref": "#/$defs/phase"},
                },
                "evidence_requirements": {
                    "type": "array",
                    "maxItems": 27,
                    "items": {"$ref": "#/$defs/evidence_requirement"},
                },
            },
            "$defs": {
                "phase": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "requires",
                        "allowed_next",
                        "required_kinds",
                        "envelope",
                    ],
                    "properties": {
                        "name": IDENTIFIER,
                        "requires": {"type": "array", "uniqueItems": True, "items": IDENTIFIER},
                        "allowed_next": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": IDENTIFIER,
                        },
                        "required_kinds": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"enum": sorted(EVENT_KINDS)},
                        },
                        "max_duration_ns": {"type": "integer", "minimum": 1},
                        "envelope": {"$ref": "#/$defs/envelope"},
                    },
                },
                "envelope": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["allowed_contact_states", "require_wrench_on_contact"],
                    "properties": {
                        "allowed_contact_states": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"enum": sorted(CONTACT_STATES)},
                        },
                        "require_wrench_on_contact": {"type": "boolean"},
                        "force_abs_max_n": deepcopy(POSITIVE_VEC3),
                        "force_norm_max_n": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "maximum": 1000000000,
                        },
                        "torque_abs_max_nm": deepcopy(POSITIVE_VEC3),
                        "torque_norm_max_nm": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "maximum": 1000000000,
                        },
                    },
                },
                "evidence_requirement": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "environments", "min_count"],
                    "properties": {
                        "kind": {"enum": sorted(EVIDENCE_KINDS)},
                        "environments": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 2,
                            "uniqueItems": True,
                            "items": {"enum": sorted(ENVIRONMENTS)},
                        },
                        "min_count": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                },
            },
        }
    )
    return schema


def _evidence_schema() -> dict[str, Any]:
    schema = _root("evidence")
    schema.update(
        {
            "required": ["schema_version", "items"],
            "properties": {
                "schema_version": {"const": "1.0"},
                "items": {
                    "type": "array",
                    "maxItems": 2048,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "kind", "sha256", "applies_to"],
                        "properties": {
                            "id": IDENTIFIER,
                            "kind": {"enum": sorted(EVIDENCE_KINDS)},
                            "sha256": SHA256,
                            "applies_to": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 2,
                                "uniqueItems": True,
                                "items": {"enum": sorted(ENVIRONMENTS)},
                            },
                            "source_uri": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "pattern": "^[^\\u0000-\\u001f]+$",
                            },
                        },
                    },
                },
            },
        }
    )
    return schema


def _receipt_schema() -> dict[str, Any]:
    schema = _root("receipt")
    schema.update(
        {
            "required": [
                "schema_version",
                "receipt_type",
                "tool",
                "subject",
                "input_fingerprints",
                "verdict",
                "counts",
                "phase_summary",
                "evidence_checklist",
                "violations",
                "failure_replay",
                "receipt_id",
            ],
            "properties": {
                "schema_version": {"const": "1.0"},
                "receipt_type": {"const": "contactreceipt.audit"},
                "tool": {"$ref": "#/$defs/tool"},
                "subject": {"$ref": "#/$defs/subject"},
                "input_fingerprints": {"$ref": "#/$defs/input_fingerprints"},
                "verdict": {"enum": ["fail", "pass"]},
                "counts": {"$ref": "#/$defs/counts"},
                "phase_summary": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 128,
                    "items": {"$ref": "#/$defs/phase_summary"},
                },
                "evidence_checklist": {
                    "type": "array",
                    "maxItems": 27,
                    "items": {"$ref": "#/$defs/evidence_checklist"},
                },
                "violations": {
                    "type": "array",
                    "maxItems": 1000,
                    "items": {"$ref": "#/$defs/violation"},
                },
                "failure_replay": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/failure_replay"}]},
                "receipt_id": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            },
            "$defs": {
                "tool": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "version", "algorithm"],
                    "properties": {
                        "name": {"const": "contactreceipt"},
                        "version": {"const": "0.1.0"},
                        "algorithm": {"const": "civil-assembly-v1"},
                    },
                },
                "subject": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["run_id", "assembly_id", "environment", "source_format"],
                    "properties": {
                        "run_id": deepcopy(IDENTIFIER),
                        "assembly_id": deepcopy(IDENTIFIER),
                        "environment": {"enum": sorted(ENVIRONMENTS)},
                        "source_format": {"enum": sorted(SOURCE_FORMATS)},
                    },
                },
                "input_fingerprints": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["trace_sha256", "policy_sha256", "evidence_sha256"],
                    "properties": {
                        "trace_sha256": deepcopy(SHA256),
                        "policy_sha256": deepcopy(SHA256),
                        "evidence_sha256": deepcopy(SHA256),
                    },
                },
                "counts": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "events",
                        "phases_completed",
                        "violations",
                        "violations_truncated",
                    ],
                    "properties": {
                        "events": {"type": "integer", "minimum": 1, "maximum": 100000},
                        "phases_completed": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 128,
                        },
                        "violations": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 1000,
                        },
                        "violations_truncated": {"type": "boolean"},
                    },
                },
                "phase_summary": {
                    "oneOf": [
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "phase",
                                "status",
                                "start_ns",
                                "end_ns",
                                "duration_ns",
                            ],
                            "properties": {
                                "phase": deepcopy(IDENTIFIER),
                                "status": {"const": "completed"},
                                "start_ns": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 9223372036854775807,
                                },
                                "end_ns": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 9223372036854775807,
                                },
                                "duration_ns": {
                                    "type": "integer",
                                    "minimum": -9223372036854775807,
                                    "maximum": 9223372036854775807,
                                },
                            },
                        },
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["phase", "status", "start_ns"],
                            "properties": {
                                "phase": deepcopy(IDENTIFIER),
                                "status": {"const": "active"},
                                "start_ns": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 9223372036854775807,
                                },
                            },
                        },
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["phase", "status"],
                            "properties": {
                                "phase": deepcopy(IDENTIFIER),
                                "status": {"enum": ["entered_invalid", "not_started"]},
                            },
                        },
                    ]
                },
                "evidence_checklist": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "kind",
                        "environment",
                        "min_count",
                        "matched_ids",
                        "satisfied",
                    ],
                    "properties": {
                        "kind": {"enum": sorted(EVIDENCE_KINDS)},
                        "environment": {"enum": sorted(ENVIRONMENTS)},
                        "min_count": {"type": "integer", "minimum": 1, "maximum": 100},
                        "matched_ids": {
                            "type": "array",
                            "maxItems": 2048,
                            "uniqueItems": True,
                            "items": deepcopy(IDENTIFIER),
                        },
                        "satisfied": {"type": "boolean"},
                    },
                },
                "violation": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["code", "severity", "path", "message"],
                    "properties": {
                        "code": {"enum": VIOLATION_CODES},
                        "severity": {"const": "error"},
                        "path": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "pattern": "^/[^\\u0000-\\u001f]*$",
                        },
                        "message": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 512,
                            "pattern": "^[^\\u0000-\\u001f]+$",
                        },
                        "event_index": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 99999,
                        },
                        "event_seq": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 99999,
                        },
                        "phase": deepcopy(IDENTIFIER),
                    },
                },
                "failure_replay": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["first_code", "end_index", "end_seq", "prefix_sha256"],
                    "properties": {
                        "first_code": {"enum": VIOLATION_CODES},
                        "end_index": {
                            "oneOf": [
                                {"type": "null"},
                                {"type": "integer", "minimum": 0, "maximum": 99999},
                            ]
                        },
                        "end_seq": {
                            "oneOf": [
                                {"type": "null"},
                                {"type": "integer", "minimum": 0, "maximum": 99999},
                            ]
                        },
                        "prefix_sha256": {"oneOf": [{"type": "null"}, deepcopy(SHA256)]},
                    },
                },
            },
        }
    )
    return schema


_SCHEMAS = {
    "trace": _trace_schema(),
    "policy": _policy_schema(),
    "evidence": _evidence_schema(),
    "receipt": _receipt_schema(),
}


def schema_for(kind: str) -> dict[str, Any]:
    """Return a defensive copy of a bundled schema."""
    try:
        return deepcopy(_SCHEMAS[kind])
    except KeyError as exc:
        raise ValueError(f"unknown schema kind: {safe_label(kind)}") from exc
