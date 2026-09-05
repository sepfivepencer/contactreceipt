from __future__ import annotations

import json
from pathlib import Path

import pytest

from contactreceipt.cli import main

ROOT = Path(__file__).parents[1]


def _args(trace: str, output: Path) -> list[str]:
    return [
        "validate",
        "--trace",
        str(ROOT / "examples" / trace),
        "--policy",
        str(ROOT / "examples" / "policy.json"),
        "--evidence",
        str(ROOT / "examples" / "evidence.json"),
        "--output",
        str(output),
    ]


def test_cli_pass_writes_receipt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "receipt.json"
    assert main(_args("trace-pass.json", output)) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "pass"
    summary = json.loads(capsys.readouterr().out)
    assert summary["violations"] == 0


def test_cli_fail_writes_receipt(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    assert main(_args("trace-fail.json", output)) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "fail"


def test_cli_quiet_suppresses_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "receipt.json"
    assert main([*_args("trace-pass.json", output), "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_cli_preflights_output_before_reading_inputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("keep", encoding="utf-8")
    args = _args("missing.json", output)
    assert main(args) == 2
    assert "overwrite" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "keep"


def test_cli_invalid_input_does_not_create_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "bad.json"
    source.write_text("[]", encoding="utf-8")
    output = tmp_path / "receipt.json"
    args = _args("trace-pass.json", output)
    args[2] = str(source)
    assert main(args) == 2
    assert not output.exists()
    assert "root must be an object" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("payload", "needle"),
    [
        ('{"schema_version":' + "9" * 101 + "}", "too many digits"),
        ('{"schema_version":"\\ud800"}', "lone surrogate"),
    ],
)
def test_cli_boundary_errors_exit_two_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: str,
    needle: str,
) -> None:
    source = tmp_path / "bad.json"
    source.write_text(payload, encoding="utf-8")
    output = tmp_path / "receipt.json"
    args = _args("trace-pass.json", output)
    args[2] = str(source)
    assert main(args) == 2
    captured = capsys.readouterr()
    assert needle in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()


@pytest.mark.parametrize("kind", ["trace", "policy", "evidence", "receipt"])
def test_cli_writes_each_schema(tmp_path: Path, kind: str) -> None:
    output = tmp_path / f"{kind}.schema.json"
    assert main(["schema", kind, "--output", str(output), "--quiet"]) == 0
    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")


def test_cli_schema_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "schema.json"
    output.write_text("keep", encoding="utf-8")
    assert main(["schema", "trace", "--output", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "keep"


def test_cli_verify_accepts_generated_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt = tmp_path / "receipt.json"
    assert main([*_args("trace-pass.json", receipt), "--quiet"]) == 0
    assert main(["verify", "--receipt", str(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == {"valid": True}


def test_cli_verify_rejects_tampered_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt = tmp_path / "receipt.json"
    assert main([*_args("trace-pass.json", receipt), "--quiet"]) == 0
    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["verdict"] = "fail"
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert main(["verify", "--receipt", str(receipt)]) == 1
    assert json.loads(capsys.readouterr().out) == {"valid": False}


def test_cli_verify_quiet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"receipt_id":"bad"}', encoding="utf-8")
    assert main(["verify", "--receipt", str(receipt), "--quiet"]) == 1
    assert capsys.readouterr().out == ""


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    assert "0.1.0" in capsys.readouterr().out
