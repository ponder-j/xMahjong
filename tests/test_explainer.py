import json

import pytest
from xmahjong.analysis import analyze
from xmahjong.config import Settings
from xmahjong.explainer import Claim, chat, explain, validate_claim, validate_explanation


def test_evidence_reference_guard():
    facts = {
        "f1": {"kind": "fact", "text": "计算得到向听 2，进张 20 枚。"},
        "u1": {"kind": "unknown", "text": "未知对手手牌。"},
    }
    with pytest.raises(ValueError, match="不存在"):
        validate_claim(Claim(kind="fact", text="伪造", evidence_ids=["fake"]), facts)
    result = validate_claim(Claim(kind="fact", text="模型乱写的事实", evidence_ids=["f1"]), facts)
    assert result["text"] == facts["f1"]["text"]
    with pytest.raises(ValueError, match="未知"):
        validate_claim(Claim(kind="fact", text="已知", evidence_ids=["u1"]), facts)
    with pytest.raises(ValueError, match="数字"):
        validate_claim(Claim(kind="inference", text="放铳率 98.7%", evidence_ids=["f1"]), facts)
    rounded = {"score": {"kind": "fact", "text": "Akochan 期望值 4.615993022918701（非概率）。"}}
    assert validate_claim(Claim(kind="inference", text="该期望值约 4.616。", evidence_ids=["score"]), rounded)
    with pytest.raises(ValueError, match="数字"):
        validate_claim(Claim(kind="inference", text="放铳率 4.616%。", evidence_ids=["score"]), rounded)
    metrics = {
        "c3.value": {"kind": "fact", "text": "打 E 保留宝牌 0 张。"},
        "c3.speed": {"kind": "fact", "text": "打 E 向听 2，未见进张 20 枚。"},
    }
    result = validate_claim(
        Claim(kind="inference", text="保留宝牌 0 张，未见进张 20 枚。", evidence_ids=["c3.value"]), metrics
    )
    assert set(result["evidence_ids"]) == {"c3.value", "c3.speed"}
    with pytest.raises(ValueError, match="数字"):
        validate_claim(Claim(kind="inference", text="进张 99 枚。", evidence_ids=["c3.value"]), metrics)


async def test_missing_candidate_and_unreachable_llm(events, decision, tmp_path):
    cfg = Settings(data_dir=tmp_path, llm_base_url="http://127.0.0.1:1/v1", llm_timeout=0.2)
    report = await analyze(events, decision, cfg)
    with pytest.raises(ValueError, match="全部候选"):
        validate_explanation(
            json.dumps(
                {
                    "summary": [{"kind": "fact", "text": "", "evidence_ids": ["D0"]}],
                    "candidates": [],
                    "disagreement": [{"kind": "unknown", "text": "", "evidence_ids": ["B0"]}],
                }
            ),
            report,
            report["candidates"],
        )
    result = await explain(report, cfg)
    assert result["source"] == "computed"
    result = await chat(report, "未来会摸到什么？", [], cfg)
    assert result["source"] == "computed" and result["claims"][0]["kind"] == "unknown"
