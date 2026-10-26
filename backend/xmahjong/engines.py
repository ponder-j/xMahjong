"""Native MJAI adapters. Scores never cross model scales; no synthetic model fallback."""

import asyncio
import json
import math
import os
import uuid
from collections import Counter

from .config import EngineConfig, Settings
from .tiles import RED, TILES, action_label, base, index


def choose_tiles(hand: list[str], bases: list[str]) -> list[str]:
    available, result = list(hand), []
    for wanted in bases:
        options = sorted((t for t in available if base(t) == wanted), key=lambda t: t not in RED)
        if not options:
            raise ValueError("模型动作无法从当前手牌构造")
        result.append(options[0])
        available.remove(options[0])
    return result


def mortal_action(label: int, s: dict) -> dict:
    actor, trigger = s["actor"], s["trigger"]
    target, tile = trigger.get("actor", actor), trigger.get("pai")
    if label <= 36:
        pai = TILES[label] if label < 34 else ("5mr", "5pr", "5sr")[label - 34]
        return {
            "type": "dahai",
            "actor": actor,
            "pai": pai,
            "tsumogiri": trigger["type"] == "tsumo" and pai == tile,
        }
    if label == 37:
        return {"type": "reach", "actor": actor}
    if label in (38, 39, 40):
        i = index(tile)
        offsets = {38: (1, 2), 39: (-1, 1), 40: (-2, -1)}[label]
        consumed = choose_tiles(s["hand"], [TILES[i + x] for x in offsets])
        return {"type": "chi", "actor": actor, "target": target, "pai": tile, "consumed": consumed}
    if label == 41:
        return {
            "type": "pon",
            "actor": actor,
            "target": target,
            "pai": tile,
            "consumed": choose_tiles(s["hand"], [base(tile)] * 2),
        }
    if label == 42:
        if target != actor:
            return {
                "type": "daiminkan",
                "actor": actor,
                "target": target,
                "pai": tile,
                "consumed": choose_tiles(s["hand"], [base(tile)] * 3),
            }
        possible = [t for t, n in Counter(base(t) for t in s["hand"]).items() if n == 4]
        if len(possible) == 1:
            return {"type": "ankan", "actor": actor, "consumed": choose_tiles(s["hand"], [possible[0]] * 4)}
        for meld in s["melds"][actor]:
            if meld["type"] == "pon" and any(base(t) == base(meld["pai"]) for t in s["hand"]):
                return {
                    "type": "kakan",
                    "actor": actor,
                    "pai": choose_tiles(s["hand"], [base(meld["pai"])])[0],
                    "consumed": [meld["pai"], *meld["consumed"]],
                }
        raise ValueError("杠选择需要 kan_select 元数据")
    if label == 43:
        return {"type": "hora", "actor": actor, "target": target}
    if label == 44:
        return {"type": "ryukyoku"}
    if label == 45:
        return {"type": "none"}
    raise ValueError("未知 Mortal 动作标签")


def masked_values(meta: dict) -> list[tuple[int, float]]:
    mask = meta.get("mask_bits", 0)
    labels = [i for i in range(46) if mask & (1 << i)]
    values = meta.get("q_values", [])
    if len(labels) != len(values) or any(not math.isfinite(v) for v in values):
        raise ValueError("Mortal mask/q_values 维度或数值无效")
    return list(zip(labels, values, strict=True))


def parse_mortal(raw: dict, s: dict, temperature: float) -> list[dict]:
    meta = raw.get("meta", {})
    pairs = masked_values(meta)
    candidates = []
    for label, value in pairs:
        if label == 42 and s["trigger"].get("actor") == s["actor"] and meta.get("kan_select"):
            kan_pairs = masked_values(meta["kan_select"])
            for kan_label, kan_q in kan_pairs:
                if kan_label >= 34:
                    raise ValueError("无效的 kan_select 标签")
                tile = TILES[kan_label]
                if sum(base(t) == tile for t in s["hand"]) == 4:
                    action = {
                        "type": "ankan",
                        "actor": s["actor"],
                        "consumed": choose_tiles(s["hand"], [tile] * 4),
                    }
                else:
                    meld = next(
                        m for m in s["melds"][s["actor"]] if m["type"] == "pon" and base(m["pai"]) == tile
                    )
                    action = {
                        "type": "kakan",
                        "actor": s["actor"],
                        "pai": choose_tiles(s["hand"], [tile])[0],
                        "consumed": [meld["pai"], *meld["consumed"]],
                    }
                candidates.append(
                    {
                        "moves": [action],
                        "score": value if len(kan_pairs) == 1 else kan_q,
                        "raw": {
                            "label": label,
                            "kan_label": kan_label,
                            "q_value": kan_q,
                            "root_q_value": value,
                        },
                    }
                )
        else:
            candidates.append(
                {
                    "moves": [mortal_action(label, s)],
                    "score": value,
                    "raw": {"label": label, "q_value": value},
                }
            )
    if not candidates:
        return []
    maximum = max(c["score"] for c in candidates)
    weights = [math.exp((c["score"] - maximum) / temperature) for c in candidates]
    total = sum(weights)
    for c, w in zip(candidates, weights, strict=True):
        c["probability"] = w / total
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return [{**c, "rank": i + 1, "label": action_label(c["moves"])} for i, c in enumerate(candidates)]


def parse_akochan(raw: list) -> list[dict]:
    candidates = []
    for i, entry in enumerate(raw):
        if not entry.get("moves"):
            raise ValueError("Akochan 返回空动作")
        score = entry.get("review", {}).get("pt_exp_total")
        if score is not None and (not isinstance(score, (float, int)) or not math.isfinite(score)):
            raise ValueError("Akochan 返回无效评分")
        candidates.append(
            {
                "moves": entry["moves"],
                "score": score,
                "probability": None,
                "rank": i + 1,
                "label": action_label(entry["moves"]),
                "raw": entry,
            }
        )
    return candidates


async def run_engine(name: str, config: EngineConfig, events: list[dict], s: dict, cfg: Settings) -> dict:
    result = {
        "name": name,
        "version": config.version,
        "weight_sha256": config.weight_sha256,
        "score_kind": "q_value" if name == "mortal" else "pt_exp_total",
        "temperature": cfg.temperature if name == "mortal" else None,
        "status": "unconfigured",
        "candidates": [],
        "message": "未配置引擎命令或模型权重",
    }
    if not config.command:
        return result
    if name == "akochan" and s["trigger"]["type"] not in ("tsumo", "dahai", "kakan"):
        result.update(
            status="unsupported",
            message="Akochan 原生接口不支持此独立决策阶段；请在吃碰或立直前查看其完整复合动作评价",
        )
        return result
    container_name = "xmahjong-" + uuid.uuid4().hex[:16]
    command = [part.replace("{actor}", str(s["actor"])) for part in config.command]
    is_docker = (
        os.path.basename(command[0]).lower() in ("docker", "docker.exe")
        and len(command) > 1
        and command[1] == "run"
    )
    if is_docker:
        command[2:2] = ["--name", container_name]
    env = {**os.environ, **config.env}
    if name == "mortal":
        env["MORTAL_REVIEW_MODE"] = "1"
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=config.cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **({"creationflags": 0x08000000} if os.name == "nt" else {}),
        )
        data = ("\n".join(json.dumps(e) for e in events) + "\n").encode()
        # Mortal review CLI may attempt GRP after EOF. Read the decision response first,
        # then terminate without asking for a whole-game placement model.
        if name == "mortal":

            async def exchange():
                raw = None
                for event_index, event in enumerate(events):
                    # Upstream Bot.react accepts can_act=false to update its state
                    # without reevaluating every historical decision in this prefix.
                    payload = {**event, "can_act": event_index == len(events) - 1}
                    proc.stdin.write((json.dumps(payload) + "\n").encode())
                    await proc.stdin.drain()
                    line = await proc.stdout.readline()
                    if not line:
                        raise ValueError("Mortal 提前退出，检查 checkpoint 和 libriichi")
                    raw = json.loads(line)
                return raw

            # Drain stderr concurrently to avoid pipe deadlock; no credentials are returned.
            drain = asyncio.create_task(proc.stderr.read())
            try:
                raw = await asyncio.wait_for(exchange(), config.timeout)
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
                await drain
            candidates = parse_mortal(raw, s, cfg.temperature)
        else:
            out, _ = await asyncio.wait_for(proc.communicate(data), config.timeout)
            if proc.returncode:
                raise ValueError("Akochan 进程失败；请检查工作目录、参数和共享库")
            lines = [json.loads(line) for line in out.decode().splitlines() if line.strip().startswith("[")]
            if not lines:
                raise ValueError("Akochan 未在该时点输出候选")
            raw = lines[-1]
            candidates = parse_akochan(raw)
        result.update(
            status="ok" if candidates else "no_candidates",
            candidates=candidates,
            raw_output=raw,
            message="真实引擎输出" if candidates else "引擎未返回可选动作",
        )
    except TimeoutError:
        result.update(status="timeout", message=f"推理超过 {config.timeout:g} 秒，已终止")
    except (OSError, ValueError, KeyError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        result.update(status="error", message=str(exc)[:200])
    finally:
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.wait()
        if is_docker and proc is not None:
            cleanup = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "-f",
                container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await cleanup.wait()
    return result
