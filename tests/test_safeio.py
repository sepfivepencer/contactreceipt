from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from contactreceipt import safeio
from contactreceipt.errors import InputError, OutputError, safe_label
from contactreceipt.safeio import ensure_output_available, load_json, safe_write_json


def test_load_json_reads_regular_file(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text('{"hello":"世界"}', encoding="utf-8")
    assert load_json(source) == {"hello": "世界"}


def test_load_json_rejects_duplicate_keys(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text('{"x":1,"x":2}', encoding="utf-8")
    with pytest.raises(InputError, match="duplicate"):
        load_json(source)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_load_json_rejects_non_finite_constants(tmp_path: Path, constant: str) -> None:
    source = tmp_path / "input.json"
    source.write_text(f'{{"x":{constant}}}', encoding="utf-8")
    with pytest.raises(InputError, match="non-finite"):
        load_json(source)


def test_load_json_rejects_invalid_utf8(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(b"\xff")
    with pytest.raises(InputError, match="UTF-8"):
        load_json(source)


def test_load_json_rejects_invalid_json(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text("{", encoding="utf-8")
    with pytest.raises(InputError, match="invalid JSON"):
        load_json(source)


def test_load_json_rejects_too_long_integer_as_input_error(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text('{"x":' + "9" * 101 + "}", encoding="utf-8")
    with pytest.raises(InputError, match="too many digits"):
        load_json(source)


def test_load_json_rejects_overflowing_exponent(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text('{"x":1e999}', encoding="utf-8")
    with pytest.raises(InputError, match="non-finite"):
        load_json(source)


@pytest.mark.parametrize("payload", ['{"x":"\\ud800"}', '{"\\udfff":1}'])
def test_load_json_rejects_lone_surrogates(tmp_path: Path, payload: str) -> None:
    source = tmp_path / "input.json"
    source.write_text(payload, encoding="utf-8")
    with pytest.raises(InputError, match="lone surrogate"):
        load_json(source)


def test_load_json_rejects_large_file(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text("12345", encoding="utf-8")
    with pytest.raises(InputError, match="exceeds"):
        load_json(source, max_bytes=4)


def test_load_json_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        load_json(tmp_path)


def test_load_json_rejects_final_symlink(tmp_path: Path) -> None:
    source = tmp_path / "real.json"
    source.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(source)
    with pytest.raises(InputError):
        load_json(link)


def test_safe_write_is_canonical_and_private(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    safe_write_json(output, {"z": 1, "a": "值"})
    assert output.read_bytes() == '{"a":"值","z":1}\n'.encode()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_safe_write_refuses_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("keep", encoding="utf-8")
    with pytest.raises(OutputError, match="overwrite"):
        safe_write_json(output, {"new": True})
    assert output.read_text(encoding="utf-8") == "keep"


def test_safe_write_refuses_symlink_target(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text("keep", encoding="utf-8")
    output = tmp_path / "receipt.json"
    output.symlink_to(real)
    with pytest.raises(OutputError, match="overwrite"):
        safe_write_json(output, {"new": True})
    assert real.read_text(encoding="utf-8") == "keep"


def test_safe_write_refuses_symlink_parent(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(OutputError, match="unsafe"):
        safe_write_json(linked_parent / "receipt.json", {"new": True})
    assert not (real_parent / "receipt.json").exists()


def test_output_parent_must_exist(tmp_path: Path) -> None:
    with pytest.raises(OutputError, match="does not exist"):
        ensure_output_available(tmp_path / "missing" / "out.json")


def test_output_must_name_file(tmp_path: Path) -> None:
    with pytest.raises(OutputError):
        ensure_output_available(tmp_path / ".")


def test_safe_write_rejects_large_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safeio, "MAX_OUTPUT_BYTES", 2)
    with pytest.raises(OutputError, match="exceeds"):
        safe_write_json(tmp_path / "out.json", {"x": 1})


def test_safe_write_race_does_not_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "out.json"
    original_link = os.link

    def racing_link(*args: object, **kwargs: object) -> None:
        output.write_text("racer", encoding="utf-8")
        original_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(OutputError, match="overwrite"):
        safe_write_json(output, {"x": 1})
    assert output.read_text(encoding="utf-8") == "racer"
    assert not list(tmp_path.glob(".out.json.tmp-*"))


def test_safe_write_parent_replacement_race_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    moved = tmp_path / "moved-parent"
    output = parent / "out.json"
    original_link = os.link

    def racing_link(*args: object, **kwargs: object) -> None:
        parent.rename(moved)
        parent.symlink_to(attacker, target_is_directory=True)
        original_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(OutputError, match="parent directory"):
        safe_write_json(output, {"x": 1})
    assert not (attacker / "out.json").exists()
    assert not (moved / "out.json").exists()
    assert not list(moved.glob(".out.json.tmp-*"))


def test_load_json_missing_file_uses_basename_only(tmp_path: Path) -> None:
    missing = tmp_path / "secret-parent" / "missing.json"
    with pytest.raises(InputError) as caught:
        load_json(missing)
    assert "secret-parent" not in str(caught.value)


def test_untrusted_filename_is_ascii_escaped_and_bounded(tmp_path: Path) -> None:
    missing = tmp_path / ("bad\x1b\n" + ("x" * 180) + ".json")
    with pytest.raises(InputError) as caught:
        load_json(missing)
    message = str(caught.value)
    assert "\x1b" not in message
    assert "\n" not in message
    assert "\\u001b" in message
    assert "\\n" in message
    assert message.isascii()
    assert len(message) <= 130


def test_duplicate_key_message_is_ascii_escaped_and_bounded(tmp_path: Path) -> None:
    key = "\\u001b" + ("x" * 180)
    source = tmp_path / "input.json"
    source.write_text(f'{{"{key}":1,"{key}":2}}', encoding="utf-8")
    with pytest.raises(InputError) as caught:
        load_json(source)
    message = str(caught.value)
    assert "\x1b" not in message
    assert "\\u001b" in message
    assert message.isascii()
    assert len(message) <= 120


def test_safe_label_never_splits_escape_and_is_bounded() -> None:
    result = safe_label("a" * 100 + "\x1b", max_chars=20)
    assert result == '"aaaaaaaaaaaaaaa..."'
    assert len(result) == 20


def test_written_json_is_valid(tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    safe_write_json(output, {"a": [1, 2, 3]})
    assert json.loads(output.read_text(encoding="utf-8")) == {"a": [1, 2, 3]}
