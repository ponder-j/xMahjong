from copy import deepcopy

import pytest
from xmahjong.config import Settings
from xmahjong.logs import convert_tenhou, parse_link, parse_payload, validate


def test_supported_link_and_host_validation():
    uuid = "250211-5a117214-86b4-4143-bb62-6d383d0329e8"
    assert parse_link(f"https://game.maj-soul.com/1/?paipu={uuid}_a123") == uuid
    for bad in ["https://evil-maj-soul.com/?paipu=" + uuid, "https://game.maj-soul.com/", "file:///foo"]:
        with pytest.raises(ValueError):
            parse_link(bad)


async def test_unsupported_rules_are_rejected_before_engine_launch():
    for display in ["四人東", "Silver Room East", "四人东"]:
        with pytest.raises(ValueError, match="半庄"):
            await convert_tenhou({"name": ["A", "B", "C", "D"], "rule": {"disp": display}}, Settings())
    with pytest.raises(ValueError, match="四人"):
        await convert_tenhou({"name": ["A", "B", "C"], "rule": {"disp": "南"}}, Settings())


def test_malformed_and_tonpuu_mjai(events):
    for invalid in [[None] * 4, {"a": 1}, events[:3]]:
        with pytest.raises(ValueError):
            validate(invalid)
    east = deepcopy(events)
    east[0]["kyoku_first"] = 4  # convlog GameLength::Tonpuu; Hanchan is 0.
    with pytest.raises(ValueError, match="东风"):
        validate(east)


async def test_invalid_encoding():
    with pytest.raises(ValueError):
        await parse_payload(b"\xff\xfe\x00", Settings())
