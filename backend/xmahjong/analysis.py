import asyncio
from copy import deepcopy

from .config import Settings
from .engines import run_engine
from .evidence import all_discard_evidence
from .state import masked_prefix
from .tiles import action_key, action_label


def first_key(moves: list[dict]) -> str:
    return action_key(moves[0])


def disagreement(engines: list[dict]) -> dict:
    usable = [e for e in engines if e["status"] == "ok" and e["candidates"]]
    if len(usable) < 2:
        return {"level": "unknown", "label": "证据不足", "reason": "两个引擎都成功返回候选后才能比较分歧。"}
    tops = [first_key(e["candidates"][0]["moves"]) for e in usable]
    if len(set(tops)) == 1:
        return {
            "level": "consensus",
            "label": "模型共识",
            "reason": "两个引擎的首选动作一致；复合动作后续弃牌仍需分别核查。",
        }
    mutual = all(
        any(first_key(c["moves"]) == tops[1 - i] for c in usable[i]["candidates"][:2]) for i in range(2)
    )
    return {
        "level": "minor" if mutual else "conflict",
        "label": "轻微分歧" if mutual else "明显冲突",
        "reason": "首选不同，但互相均进入前二。" if mutual else "首选不同，且至少一方未将对方首选排入前二。",
    }


def merge_candidates(engines: list[dict], actual: list[dict], top_k: int) -> list[dict]:
    result = {}
    for engine in engines:
        for c in engine["candidates"]:
            p = c.get("probability")
            selected = p >= 0.01 if p is not None else c["rank"] <= top_k
            if selected:
                key = action_key(c["moves"])
                result.setdefault(key, {"key": key, "moves": c["moves"], "reasons": []})
                result[key]["reasons"].append(
                    f"{engine['name']} ≥1%" if p is not None else f"{engine['name']} Top-{top_k}"
                )
    key = action_key(actual)
    result.setdefault(key, {"key": key, "moves": actual, "reasons": []})
    result[key]["reasons"].append("玩家实际动作")
    for i, c in enumerate(result.values()):
        c.update(id=f"c{i + 1}", actual=c["key"] == key, label=action_label(c["moves"]), models={})
        for engine in engines:
            match = next((d for d in engine["candidates"] if action_key(d["moves"]) == c["key"]), None)
            c["models"][engine["name"]] = deepcopy(match) if match else None
    return list(result.values())


def make_facts(report: dict) -> dict:
    facts = {
        "B0": {
            "kind": "unknown",
            "text": "未知对手手牌、后续摸牌、完整打点期望与真实放铳概率。不能据此断言模型内部理由。",
        },
        "D0": {
            "kind": "fact",
            "text": report["disagreement"]["label"] + "：" + report["disagreement"]["reason"],
        },
    }
    for c in report["candidates"]:
        prefix, e = c["id"], c.get("evidence")
        if e:
            facts[prefix + ".speed"] = {
                "kind": "fact",
                "text": f"{c['label']}：弃牌后向听 {e['shanten']}，减少向听的未见进张 {e['ukeire']} 枚。",
            }
            facts[prefix + ".value"] = {
                "kind": "fact",
                "text": f"{c['label']}：保留宝牌 {e['retained_dora']} 张、赤牌 {e['retained_red']} 张；这不是完整打点。",
            }
            safe = [str(r["opponent"]) for r in e["safety"] if r["genbutsu"]]
            facts[prefix + ".safety"] = {
                "kind": "fact",
                "text": f"{c['label']}："
                + (
                    f"对座位 {','.join(safe)} 有现物依据；其余对手危险度未知。"
                    if safe
                    else "没有可确认的对手现物依据；危险度未知。"
                ),
            }
        for name, score in c["models"].items():
            if score:
                p = score.get("probability")
                facts[prefix + "." + name] = {
                    "kind": "fact",
                    "text": f"{name} 对 {c['label']} 排名 {score['rank']}，原生评分 {score['score']}"
                    + (f"，偏好 {p:.4%}（非胜率）" if p is not None else "（非概率）")
                    + "。",
                }
    measured = [c for c in report["candidates"] if c.get("evidence")]
    for c in measured:
        others = [o for o in measured if o["id"] != c["id"]]
        if not others:
            continue
        peer = min(others, key=lambda o: (o["evidence"]["shanten"], -o["evidence"]["ukeire"]))
        e, p = c["evidence"], peer["evidence"]
        text = f"{c['label']} 对照 {peer['label']}：向听为 {e['shanten']} 对 {p['shanten']}，未见进张为 {e['ukeire']} 对 {p['ukeire']} 枚。"
        text += (
            "向听不同，不能仅按进张枚数判断速度。"
            if e["shanten"] != p["shanten"]
            else "同向听下可比较这些即时进张，但未计算后续改良。"
        )
        facts[c["id"] + ".comparison"] = {"kind": "fact", "text": text}
    return facts


def deterministic_explanation(report: dict) -> dict:
    candidates = []
    measured = [c["evidence"] for c in report["candidates"] if c.get("evidence")]
    best_shanten = min((e["shanten"] for e in measured), default=None)
    best_ukeire = max((e["ukeire"] for e in measured if e["shanten"] == best_shanten), default=None)

    def claim(text, refs, kind="fact"):
        return {"text": text, "evidence_ids": refs, "kind": kind}

    for c in report["candidates"]:
        cid, e = c["id"], c.get("evidence")
        pros, cons, conditions, comparison = [], [], [], []
        if e:
            speed = report["facts"][cid + ".speed"]["text"]
            (pros if e["shanten"] == best_shanten else cons).append(claim(speed, [cid + ".speed"]))
            pros.append(claim(report["facts"][cid + ".value"]["text"], [cid + ".value"]))
            if any(r["genbutsu"] for r in e["safety"]):
                pros.append(claim(report["facts"][cid + ".safety"]["text"], [cid + ".safety"]))
            cons.append(
                claim("未建立对所有对手的放铳概率；宝牌数量不能代替役与点数计算。", ["B0"], "unknown")
            )
            conditions.append(
                claim(
                    "若优先保留当前进张，可比较同向听候选；若需防守，只对有现物依据的对应对手成立。",
                    [cid + ".speed", cid + ".safety"],
                    "inference",
                )
            )
            if e["shanten"] == best_shanten and e["ukeire"] == best_ukeire:
                comparison.append(
                    claim(
                        "在已测候选中，向听最少且同向听下未见进张并列最多；不能由此推出整体最优。",
                        [x["id"] + ".speed" for x in report["candidates"] if x.get("evidence")],
                        "inference",
                    )
                )
            else:
                comparison.append(
                    claim(
                        "请横向对照向听与未见进张；不能用牌效一个指标解释模型全部选择。",
                        [cid + ".speed", "B0"],
                        "inference",
                    )
                )
        else:
            cons.append(
                claim("该动作尚无独立的完整模拟证据，不能评估其速度、打点或风险变化。", ["B0"], "unknown")
            )
            conditions.append(
                claim("应结合已配置引擎的合法动作输出核查；本版本不推演该动作的未来牌山。", ["B0"], "unknown")
            )
        for name in c["models"]:
            ref = cid + "." + name
            if ref in report["facts"]:
                pros.append(claim(report["facts"][ref]["text"], [ref]))
        candidates.append(
            {
                "candidate_id": cid,
                "advantages": pros,
                "disadvantages": cons,
                "conditions": conditions,
                "comparison": comparison,
            }
        )
    return {
        "source": "computed",
        "model": None,
        "notice": "确定性证据报告；尚未调用 LLM。模型偏好不等于已证明的优劣。",
        "summary": [claim(report["facts"]["D0"]["text"], ["D0"])],
        "candidates": candidates,
        "disagreement": [
            claim(
                "排名可以确认选择差异；攻守、速度、打点动机需要相应证据支持，不能从模型名称推断。",
                ["D0", "B0"],
                "unknown",
            )
        ],
    }


async def analyze(events: list[dict], decision: dict, cfg: Settings) -> dict:
    s, end = decision["state"], decision["id"]
    prefix = masked_prefix(events, end, s["actor"])
    engines = await asyncio.gather(
        run_engine("mortal", cfg.mortal, prefix, s, cfg), run_engine("akochan", cfg.akochan, prefix, s, cfg)
    )
    evidence = await asyncio.to_thread(all_discard_evidence, s)
    candidates = merge_candidates(engines, decision["actual"], cfg.top_k)
    # With no model, useful computed comparisons remain explicitly separate from AI candidates.
    if not any(e["status"] == "ok" for e in engines):
        existing = {c["key"] for c in candidates}
        from .state import legal_discards

        for a in legal_discards(s):
            key = action_key(a)
            if key not in existing:
                candidates.append(
                    {
                        "id": f"c{len(candidates) + 1}",
                        "key": key,
                        "moves": [a],
                        "label": action_label([a]),
                        "actual": False,
                        "reasons": ["独立牌效对照（非 AI 推荐）"],
                        "models": {"mortal": None, "akochan": None},
                    }
                )
    for c in candidates:
        moves = c["moves"]
        last_discard = moves[-1] if moves[-1]["type"] == "dahai" else None
        c["evidence"] = evidence.get(action_key(last_discard)) if last_discard else None
        c["evidence_scope"] = (
            "末次弃牌的即时证据；不含复合动作的完整收益与风险"
            if len(moves) > 1
            else "即时弃牌证据"
            if c["evidence"]
            else "未实现该动作的独立完整模拟"
        )
    report = {
        "decision_id": end,
        "state": s,
        "actual": decision["actual"],
        "engines": engines,
        "candidates": candidates,
        "disagreement": disagreement(engines),
        "all_discard_evidence": evidence,
        "threshold": {"probability": 0.01, "top_k": cfg.top_k},
        "limitations": [
            "未见枚数不是活牌山枚数",
            "模型评分不同尺度，不能相减",
            "只支持合法弃牌的单步反事实，不推演未来对局",
        ],
    }
    report["facts"] = make_facts(report)
    report["explanation"] = deterministic_explanation(report)
    return report
