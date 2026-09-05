"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from contactreceipt import __version__
from contactreceipt.engine import audit
from contactreceipt.errors import ContactReceiptError, InputError, safe_label
from contactreceipt.model import parse_evidence, parse_policy, parse_trace
from contactreceipt.receipt import verify_receipt
from contactreceipt.safeio import load_json, open_json_output, safe_write_json
from contactreceipt.schemas import schema_for


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contactreceipt",
        description="Validate a neutral civil-assembly trace and issue a deterministic receipt.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="audit a trace against a policy")
    validate.add_argument("--trace", required=True, type=Path, help="neutral trace JSON")
    validate.add_argument("--policy", required=True, type=Path, help="assembly policy JSON")
    validate.add_argument("--evidence", required=True, type=Path, help="evidence manifest JSON")
    validate.add_argument("--output", required=True, type=Path, help="new receipt JSON path")
    validate.add_argument("--quiet", action="store_true", help="suppress the one-line summary")

    schema = subparsers.add_parser("schema", help="write a bundled JSON Schema")
    schema.add_argument("kind", choices=("trace", "policy", "evidence", "receipt"))
    schema.add_argument("--output", required=True, type=Path, help="new schema JSON path")
    schema.add_argument("--quiet", action="store_true", help="suppress the one-line summary")

    verify = subparsers.add_parser(
        "verify", help="verify a receipt_id integrity hash (not its full schema)"
    )
    verify.add_argument("--receipt", required=True, type=Path, help="receipt JSON path")
    verify.add_argument("--quiet", action="store_true", help="suppress the one-line result")
    return parser


def _root_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InputError(f"{safe_label(name)}: root must be an object")
    return value


def _validate(args: argparse.Namespace) -> int:
    with open_json_output(args.output) as output:
        trace_raw = _root_object(load_json(args.trace), args.trace.name)
        policy_raw = _root_object(load_json(args.policy), args.policy.name)
        evidence_raw = _root_object(load_json(args.evidence), args.evidence.name)
        receipt = audit(
            parse_trace(trace_raw),
            parse_policy(policy_raw),
            parse_evidence(evidence_raw),
        )
        output.write_json(receipt)
    if not args.quiet:
        summary = {
            "output": str(args.output),
            "receipt_id": receipt["receipt_id"],
            "verdict": receipt["verdict"],
            "violations": receipt["counts"]["violations"],
        }
        print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["verdict"] == "pass" else 1


def _schema(args: argparse.Namespace) -> int:
    safe_write_json(args.output, schema_for(args.kind))
    if not args.quiet:
        print(json.dumps({"kind": args.kind, "output": str(args.output)}, sort_keys=True))
    return 0


def _verify(args: argparse.Namespace) -> int:
    receipt = _root_object(load_json(args.receipt), args.receipt.name)
    valid = verify_receipt(receipt)
    if not args.quiet:
        print(json.dumps({"valid": valid}, sort_keys=True))
    return 0 if valid else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args)
        if args.command == "schema":
            return _schema(args)
        return _verify(args)
    except ContactReceiptError as exc:
        print(f"contactreceipt: error: {exc}", file=sys.stderr)
        return 2


def entrypoint() -> None:
    """Console-script entry point."""
    raise SystemExit(main())
