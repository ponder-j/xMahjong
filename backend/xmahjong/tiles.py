HONORS = ("E", "S", "W", "N", "P", "F", "C")
TILES = tuple(f"{n}{s}" for s in "mps" for n in range(1, 10)) + HONORS
RED = {"5mr": "5m", "5pr": "5p", "5sr": "5s"}


def base(tile: str) -> str:
    return RED.get(tile, tile)


def index(tile: str) -> int:
    return TILES.index(base(tile))


def counts(tiles: list[str]) -> list[int]:
    result = [0] * 34
    for tile in tiles:
        result[index(tile)] += 1
    return result


def sort_tiles(tiles: list[str]) -> list[str]:
    return sorted(tiles, key=lambda t: (index(t), t in RED))


def dora(marker: str) -> str:
    i = index(marker)
    if i < 27:
        return TILES[(i // 9) * 9 + (i + 1) % 9]
    if i < 31:
        return TILES[27 + (i - 26) % 4]
    return TILES[31 + (i - 30) % 3]


def action_key(action: dict | list[dict]) -> str:
    """Identity includes complete compound move; discard tedashi is not a strategic distinction."""
    import json

    moves = action if isinstance(action, list) else [action]
    clean = [
        {
            k: (sorted(v) if k == "consumed" else v)
            for k, v in a.items()
            if k in ("type", "actor", "target", "pai", "consumed")
        }
        for a in moves
    ]
    return json.dumps(clean, sort_keys=True, separators=(",", ":"))


def action_label(moves: list[dict]) -> str:
    names = {
        "dahai": "打",
        "reach": "立直",
        "chi": "吃",
        "pon": "碰",
        "ankan": "暗杠",
        "kakan": "加杠",
        "daiminkan": "大明杠",
        "hora": "和牌",
        "none": "跳过",
        "ryukyoku": "九种九牌",
    }
    return " → ".join(
        names.get(a["type"], a["type"]) + (" " + a["pai"] if a.get("pai") else "") for a in moves
    )
