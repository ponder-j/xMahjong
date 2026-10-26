import sys

import pytest
from xmahjong.analysis import disagreement, merge_candidates
from xmahjong.config import EngineConfig, Settings
from xmahjong.engines import parse_akochan, parse_mortal, run_engine


def candidate(tile, rank=1, probability=None):
    return {
        "moves": [{"type": "dahai", "actor": 0, "pai": tile}],
        "rank": rank,
        "score": 10.0 - rank,
        "probability": probability,
    }


def engine(name, candidates):
    return {"name": name, "status": "ok", "candidates": candidates}


def test_union_boundary_and_actual():
    engines = [
        engine("mortal", [candidate("1m", 1, 0.989), candidate("2m", 2, 0.01), candidate("3m", 3, 0.001)]),
        engine("akochan", [candidate("4p"), candidate("5p", 2), candidate("6p", 3)]),
    ]
    actual = [{"type": "dahai", "actor": 0, "pai": "C"}]
    result = merge_candidates(engines, actual, top_k=2)
    assert {c["moves"][0]["pai"] for c in result} == {"1m", "2m", "4p", "5p", "C"}
    assert next(c for c in result if c["actual"])["models"]["mortal"] is None
    assert next(c for c in result if c["moves"][0]["pai"] == "4p")["models"]["akochan"]["probability"] is None


def test_all_disagreement_levels():
    e1 = engine("mortal", [candidate("1m"), candidate("2m", 2)])
    assert disagreement([e1])["level"] == "unknown"
    assert disagreement([e1, engine("akochan", [candidate("1m")])])["level"] == "consensus"
    assert disagreement([e1, engine("akochan", [candidate("2m"), candidate("1m", 2)])])["level"] == "minor"
    assert disagreement([e1, engine("akochan", [candidate("3m"), candidate("4m", 2)])])["level"] == "conflict"


def test_mortal_mask_raw_and_temperature(decision):
    # Explicit synthetic protocol fixture, never used by production as a substitute model.
    raw = {
        "type": "dahai",
        "actor": 0,
        "pai": "3m",
        "meta": {"mask_bits": (1 << 2) | (1 << 6), "q_values": [0.2, 0.1]},
    }
    result = parse_mortal(raw, decision["state"], 0.1)
    assert result[0]["moves"][0]["pai"] == "3m"
    assert result[0]["score"] == 0.2
    assert result[0]["probability"] == pytest.approx(0.7310585786)
    assert sum(c["probability"] for c in result) == pytest.approx(1)
    with pytest.raises(ValueError, match="维度"):
        parse_mortal({"meta": {"mask_bits": 3, "q_values": [1]}}, decision["state"], 0.1)


def test_akochan_keeps_raw_ev_and_null():
    raw = [
        {"moves": [{"type": "none"}], "review": {"pt_exp_total": None}},
        {
            "moves": [{"type": "dahai", "actor": 0, "pai": "P"}],
            "review": {"pt_exp_total": -12.5, "total_houjuu_hai_prob_now": 0.08},
        },
    ]
    result = parse_akochan(raw)
    assert result[0]["score"] is None and result[1]["score"] == -12.5
    assert result[1]["raw"]["review"]["total_houjuu_hai_prob_now"] == 0.08
    assert all(c["probability"] is None for c in result)


async def test_unavailable_and_timeout(decision):
    result = await run_engine("mortal", EngineConfig(), [], decision["state"], Settings())
    assert result["status"] == "unconfigured" and result["candidates"] == []
    cfg = EngineConfig(command=[sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.1)
    result = await run_engine("akochan", cfg, [], decision["state"], Settings())
    assert result["status"] == "timeout" and result["candidates"] == []


async def test_native_mortal_protocol_contract(decision, tmp_path):
    script = tmp_path / "fake_protocol_only.py"
    script.write_text(
        "import sys,json\nfor line in sys.stdin:\n print(json.dumps({'type':'dahai','actor':0,'pai':'3m','meta':{'mask_bits':4,'q_values':[0.2]}}),flush=True)\n",
        encoding="utf-8",
    )
    cfg = EngineConfig(command=[sys.executable, str(script)], version="synthetic-contract-test")
    result = await run_engine("mortal", cfg, [{"type": "start_game"}], decision["state"], Settings())
    assert result["status"] == "ok" and result["candidates"][0]["score"] == 0.2


async def test_mortal_evaluates_only_target_event(decision, tmp_path):
    script = tmp_path / "assert_prefix_protocol.py"
    script.write_text(
        "import sys,json\n"
        "for i,line in enumerate(sys.stdin):\n"
        " event=json.loads(line)\n"
        " assert event['can_act']==(i==1)\n"
        " print(json.dumps({'meta':{'mask_bits':4,'q_values':[0.2]}}),flush=True)\n",
        encoding="utf-8",
    )
    cfg = EngineConfig(command=[sys.executable, str(script)], version="synthetic-contract-test")
    events = [{"type": "start_game"}, {"type": "tsumo", "actor": 0, "pai": "E"}]
    result = await run_engine("mortal", cfg, events, decision["state"], Settings())
    assert result["status"] == "ok"


async def test_akochan_explicitly_reports_unsupported_phase(decision):
    from copy import deepcopy

    state = deepcopy(decision["state"])
    state["trigger"] = {"type": "pon", "actor": 0, "target": 2, "pai": "C", "consumed": ["C", "C"]}
    config = EngineConfig(command=["nonexistent-command-must-not-run"])
    result = await run_engine("akochan", config, [], state, Settings())
    assert result["status"] == "unsupported" and result["candidates"] == []
