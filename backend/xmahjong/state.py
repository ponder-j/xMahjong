from copy import deepcopy
from dataclasses import dataclass, field

from .tiles import TILES, base, counts, index, sort_tiles


@dataclass
class State:
    hands: list[list[str]] = field(default_factory=lambda: [[], [], [], []])
    rivers: list[list[dict]] = field(default_factory=lambda: [[], [], [], []])
    melds: list[list[dict]] = field(default_factory=lambda: [[], [], [], []])
    reached: list[bool] = field(default_factory=lambda: [False] * 4)
    scores: list[int] = field(default_factory=lambda: [25000] * 4)
    turns: list[int] = field(default_factory=lambda: [0] * 4)
    dora_markers: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=lambda: ["东家", "南家", "西家", "北家"])
    bakaze: str = "E"
    kyoku: int = 1
    honba: int = 0
    kyotaku: int = 0
    oya: int = 0
    tiles_left: int = 70
    last: dict = field(default_factory=dict)

    def apply(self, e: dict):
        t, a = e["type"], e.get("actor")
        if t == "start_game":
            self.names = e.get("names", self.names)
        elif t == "start_kyoku":
            self.hands = deepcopy(e["tehais"])
            self.rivers, self.melds = [[], [], [], []], [[], [], [], []]
            self.reached, self.turns = [False] * 4, [0] * 4
            self.scores = list(e["scores"])
            self.bakaze, self.kyoku = e["bakaze"], e["kyoku"]
            self.honba, self.kyotaku, self.oya = e["honba"], e["kyotaku"], e["oya"]
            self.dora_markers = [e["dora_marker"]]
            self.tiles_left = 70
        elif t == "tsumo":
            self.hands[a].append(e["pai"])
            self.turns[a] += 1
            self.tiles_left -= 1
        elif t == "dahai":
            self._remove(a, e["pai"])
            self.rivers[a].append({"pai": e["pai"], "tsumogiri": e.get("tsumogiri", False), "called": False})
        elif t in ("chi", "pon", "daiminkan", "ankan"):
            for tile in e["consumed"]:
                self._remove(a, tile)
            self.melds[a].append(deepcopy(e))
            if t in ("chi", "pon"):
                self.turns[a] += 1
            if t != "ankan":
                river = self.rivers[e["target"]]
                if river:
                    river[-1]["called"] = True
        elif t == "kakan":
            self._remove(a, e["pai"])
            for meld in self.melds[a]:
                if meld["type"] == "pon" and base(meld["pai"]) == base(e["pai"]):
                    meld["type"] = "kakan"
                    meld["added"] = e["pai"]
                    break
            else:
                raise ValueError("加杠缺少先前的碰牌")
        elif t == "reach_accepted":
            self.reached[a] = True
            self.scores[a] -= 1000
            self.kyotaku += 1
        elif t == "dora":
            self.dora_markers.append(e["dora_marker"])
        elif t in ("hora", "ryukyoku") and e.get("deltas"):
            self.scores = [x + y for x, y in zip(self.scores, e["deltas"], strict=True)]
        self.last = deepcopy(e)

    def _remove(self, actor: int, tile: str):
        hand = self.hands[actor]
        if tile in hand:
            hand.remove(tile)
        elif "?" in hand:
            hand.remove("?")
        else:
            raise ValueError(f"牌谱不一致：座位 {actor} 手中不存在 {tile}")

    def snapshot(self, actor: int) -> dict:
        hand = self.hands[actor]
        if "?" in hand:
            raise ValueError("该座位手牌不完整，不能分析")
        return {
            "actor": actor,
            "hand": sort_tiles(hand),
            "rivers": deepcopy(self.rivers),
            "melds": deepcopy(self.melds),
            "reached": self.reached.copy(),
            "scores": self.scores.copy(),
            "turn": self.turns[actor],
            "dora_markers": self.dora_markers.copy(),
            "names": self.names.copy(),
            "bakaze": self.bakaze,
            "kyoku": self.kyoku,
            "honba": self.honba,
            "kyotaku": self.kyotaku,
            "oya": self.oya,
            "tiles_left": self.tiles_left,
            "trigger": deepcopy(self.last),
        }


def public_counts(s: dict) -> list[int]:
    """Claimed discards stay in rivers; only consumed tiles are added for melds."""
    tiles = list(s["hand"]) + list(s["dora_markers"])
    for river in s["rivers"]:
        tiles.extend(e["pai"] for e in river)
    for melds in s["melds"]:
        for meld in melds:
            tiles.extend(meld["consumed"])
            if meld.get("added"):
                tiles.append(meld["added"])
    result = counts(tiles)
    if max(result) > 4:
        raise ValueError("可见牌超过四枚，牌谱状态有误")
    return result


def legal_discards(s: dict) -> list[dict]:
    actor, trigger = s["actor"], s["trigger"]
    if trigger.get("actor") != actor or trigger["type"] not in ("tsumo", "chi", "pon", "reach"):
        return []
    hand = s["hand"]
    if s["reached"][actor]:
        return [{"type": "dahai", "actor": actor, "pai": trigger["pai"], "tsumogiri": True}]
    banned = set()
    if trigger["type"] in ("chi", "pon"):
        banned.add(base(trigger["pai"]))
        if trigger["type"] == "chi":
            consumed = sorted(index(t) for t in trigger["consumed"])
            called = index(trigger["pai"])
            if called < consumed[0] and called % 9 <= 5:
                banned.add(TILES[called + 3])
            if called > consumed[-1] and called % 9 >= 3:
                banned.add(TILES[called - 3])
    result = [
        {
            "type": "dahai",
            "actor": actor,
            "pai": tile,
            "tsumogiri": trigger["type"] == "tsumo" and tile == trigger["pai"],
        }
        for tile in sort_tiles(list(set(hand)))
        if base(tile) not in banned
    ]
    if trigger["type"] == "reach":
        from mahjong.shanten import Shanten

        valid = []
        for action in result:
            remaining = list(hand)
            remaining.remove(action["pai"])
            if Shanten().calculate_shanten(counts(remaining)) == 0:
                valid.append(action)
        return valid
    return result


def actual_after(events: list[dict], i: int, actor: int) -> list[dict]:
    relevant = [e for e in events[i + 1 : i + 8] if e["type"] not in ("dora", "reach_accepted")]
    if not relevant:
        return [{"type": "none"}]
    first = relevant[0]
    if first.get("actor") != actor:
        # Simultaneous ron can contain the selected actor after another winner.
        if first["type"] == "hora":
            for e in relevant[:3]:
                if e["type"] == "hora" and e.get("actor") == actor:
                    return [e]
        return [{"type": "none"}]
    moves = [first]
    if (
        first["type"] in ("reach", "chi", "pon")
        and len(relevant) > 1
        and relevant[1]["type"] == "dahai"
        and relevant[1].get("actor") == actor
    ):
        moves.append(relevant[1])
    return deepcopy(moves)


def decisions(events: list[dict], actor: int) -> list[dict]:
    state, result = State(), []
    for i, event in enumerate(events):
        state.apply(event)
        kind, who = event["type"], event.get("actor")
        own = who == actor and kind in ("tsumo", "chi", "pon", "reach")
        reaction = who is not None and who != actor and kind in ("dahai", "kakan")
        if own or reaction:
            if "?" in state.hands[actor]:
                continue
            result.append(
                {
                    "id": i,
                    "kind": "self" if own else "reaction",
                    "state": state.snapshot(actor),
                    "actual": actual_after(events, i, actor),
                }
            )
    return result


def masked_prefix(events: list[dict], end: int, actor: int) -> list[dict]:
    """No future events and no opponent private tiles, including start_kyoku."""
    result = deepcopy(events[: end + 1])
    for e in result:
        if e["type"] == "start_game":
            e["id"] = actor
        if e["type"] == "start_kyoku":
            e["tehais"] = [h if a == actor else ["?"] * len(h) for a, h in enumerate(e["tehais"])]
        elif e["type"] == "tsumo" and e.get("actor") != actor:
            e["pai"] = "?"
    # Native engines should only see standard MJAI fields, not arbitrary imported metadata.
    allowed = {
        "type",
        "actor",
        "target",
        "pai",
        "consumed",
        "tsumogiri",
        "tehais",
        "bakaze",
        "kyoku",
        "honba",
        "kyotaku",
        "oya",
        "scores",
        "dora_marker",
        "names",
        "id",
        "deltas",
        "ura_markers",
    }
    return [{k: v for k, v in e.items() if k in allowed} for e in result]
