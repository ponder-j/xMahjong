import json
from pathlib import Path

import pytest
from xmahjong.state import decisions


@pytest.fixture
def events():
    path = Path(__file__).parent / "fixtures" / "example.mjai.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def decision(events):
    return decisions(events, 0)[0]
