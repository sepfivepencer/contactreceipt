from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]


def _example(name: str) -> dict[str, Any]:
    value = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def trace_data() -> dict[str, Any]:
    return _example("trace-pass.json")


@pytest.fixture
def policy_data() -> dict[str, Any]:
    return _example("policy.json")


@pytest.fixture
def evidence_data() -> dict[str, Any]:
    return _example("evidence.json")
