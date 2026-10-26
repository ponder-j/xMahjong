from copy import deepcopy

import pytest
from xmahjong.evidence import all_discard_evidence, discard_evidence, shanten
from xmahjong.state import decisions, legal_discards, masked_prefix, public_counts
from xmahjong.tiles import action_key, counts, dora


def test_standard_chiitoitsu_kokushi_and_open():
    standard = ["1m", "2m", "3m", "4m", "5m", "6m", "7p", "8p", "9p", "1s", "1s", "E", "E"]
    assert shanten(tuple(counts(standard)), True) == 0
    pairs = ["1m", "1m", "3m", "3m", "5p", "5p", "7p", "7p", "9s", "9s", "E", "E", "C"]
    assert shanten(tuple(counts(pairs)), True) == 0
    orphans = ["1m", "9m", "1p", "9p", "1s", "9s", "E", "S", "W", "N", "P", "F", "C"]
    assert shanten(tuple(counts(orphans)), True) == 0
    assert shanten(tuple(counts(["1m", "2m", "3m", "1p", "2p", "3p", "1s", "2s", "3s", "C"])), False) == 0


def test_no_hindsight(events, decision):
    prefix = masked_prefix(events, decision["id"], 0)
    assert len(prefix) == decision["id"] + 1
    start = next(e for e in prefix if e["type"] == "start_kyoku")
    assert all(t == "?" for h in start["tehais"][1:] for t in h)
    assert not any("meta" in e for e in prefix)
    changed = deepcopy(events)
    changed[20]["pai"] = "9s"
    assert masked_prefix(changed, decision["id"], 0) == prefix
    visible = deepcopy(decision["state"])
    assert "hands" not in visible and "tehais" not in visible


def test_all_real_states_and_no_double_counting(events):
    for actor in range(4):
        for d in decisions(events, actor):
            assert max(public_counts(d["state"])) <= 4
    d = next(d for d in decisions(events, 0) if d["state"]["trigger"]["type"] == "pon")
    visible = public_counts(d["state"])
    # Called dragon stays in the river and only two consumed dragons are added.
    assert max(visible) <= 4


def test_ukeire_uses_only_visible_information(decision):
    s = decision["state"]
    for action in legal_discards(s):
        e = discard_evidence(s, action)
        assert e["ukeire"] == sum(t["unseen"] for t in e["effective_tiles"])
        assert all(0 < t["unseen"] <= 4 for t in e["effective_tiles"])
        assert all(x["risk_probability"] is None for x in e["safety"])
    assert len(all_discard_evidence(s)) == len(legal_discards(s))


def test_riichi_tsumogiri_and_illegal_counterfactual(decision):
    s = deepcopy(decision["state"])
    s["reached"][0] = True
    legal = legal_discards(s)
    assert len(legal) == 1 and legal[0]["pai"] == s["trigger"]["pai"]
    with pytest.raises(ValueError, match="合法弃牌"):
        discard_evidence(s, {"type": "dahai", "actor": 0, "pai": "C"})


def test_kuikae(decision):
    s = deepcopy(decision["state"])
    s["trigger"] = {"type": "chi", "actor": 0, "target": 3, "pai": "1m", "consumed": ["2m", "3m"]}
    s["hand"] = ["1m", "4m", "5mr", "7s"]
    assert {a["pai"] for a in legal_discards(s)} == {"5mr", "7s"}


def test_genbutsu_is_opponent_specific(decision):
    s = deepcopy(decision["state"])
    s["rivers"][1] = [{"pai": "3m", "called": False}]
    s["reached"][1] = True
    e = discard_evidence(s, {"type": "dahai", "actor": 0, "pai": "3m"})
    assert e["safety"][0]["genbutsu"] is True
    assert e["safety"][1]["genbutsu"] is False


def test_action_identity_and_dora():
    a = {"type": "dahai", "actor": 0, "pai": "5m", "tsumogiri": True}
    assert action_key(a) == action_key({**a, "tsumogiri": False})
    assert action_key(a) != action_key({**a, "pai": "5mr"})
    assert [dora(t) for t in ["9m", "N", "C"]] == ["1m", "E", "P"]


def test_reach_declaration_discards_keep_tenpai(decision):
    s = deepcopy(decision["state"])
    s["hand"] = ["1m", "2m", "3m", "4m", "5m", "6m", "7p", "8p", "9p", "1s", "1s", "E", "E", "9s"]
    s["trigger"] = {"type": "reach", "actor": 0}
    assert [a["pai"] for a in legal_discards(s)] == ["9s"]
