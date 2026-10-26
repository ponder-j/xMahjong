from functools import lru_cache

from mahjong.shanten import Shanten

from .state import legal_discards, public_counts
from .tiles import RED, TILES, action_key, base, counts, dora


@lru_cache(maxsize=65536)
def shanten(hand: tuple[int, ...], closed: bool) -> int:
    # Instantiate per call: Shanten holds mutable recursion state.
    return Shanten().calculate_shanten(hand, use_chiitoitsu=closed, use_kokushi=closed)


def discard_evidence(s: dict, action: dict) -> dict:
    if action_key(action) not in {action_key(a) for a in legal_discards(s)}:
        raise ValueError("反事实仅支持当前局面的合法弃牌；不能修改牌山或未来事件")
    hand = list(s["hand"])
    hand.remove(action["pai"])
    closed = all(m["type"] == "ankan" for m in s["melds"][s["actor"]])
    c = counts(hand)
    current = shanten(tuple(c), closed)
    visible = public_counts(s)
    effective = []
    waits = []
    for i in range(34):
        if c[i] >= 4:
            continue
        c[i] += 1
        new_shanten = shanten(tuple(c), closed)
        c[i] -= 1
        if new_shanten < current:
            if current == 0:
                waits.append(TILES[i])
            if visible[i] < 4:
                effective.append({"tile": TILES[i], "unseen": 4 - visible[i]})
    tile = base(action["pai"])
    safety = []
    for opponent in range(4):
        if opponent == s["actor"]:
            continue
        genbutsu = any(base(e["pai"]) == tile for e in s["rivers"][opponent])
        safety.append(
            {
                "opponent": opponent,
                "riichi": s["reached"][opponent],
                "genbutsu": genbutsu,
                "risk_probability": None,
                "assessment": "该对手的现物（仅荣和）" if genbutsu else "无现物保证，危险度未知",
            }
        )
    retained = hand.copy()
    for m in s["melds"][s["actor"]]:
        retained.extend(m["consumed"])
        if m.get("pai"):
            retained.append(m["pai"])
        if m.get("added"):
            retained.append(m["added"])
    dora_tiles = [dora(t) for t in s["dora_markers"]]
    dora_count = sum(base(t) == dt for t in retained for dt in dora_tiles)
    red_count = sum(t in RED for t in retained)
    own_river = {base(e["pai"]) for e in s["rivers"][s["actor"]]} | {tile}
    return {
        "shanten": current,
        "effective_tiles": effective,
        "ukeire": sum(e["unseen"] for e in effective),
        "ukeire_definition": "减少向听的未见牌枚数，非实际活牌山枚数；未计后续改良",
        "safety": safety,
        "retained_dora": dora_count,
        "retained_red": red_count,
        "value_note": "宝牌/赤牌不是役；未计算最终和牌点数或期望收益",
        "shape_waits": waits,
        "permanent_furiten": current == 0 and bool(set(waits) & own_river),
        "unknown": ["对手手牌", "未来摸牌", "真实放铳概率", "完整打点期望", "临时振听"],
    }


def all_discard_evidence(s: dict) -> dict[str, dict]:
    return {action_key(a): discard_evidence(s, a) for a in legal_discards(s)}
