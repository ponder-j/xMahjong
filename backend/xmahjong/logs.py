import asyncio
import json
import logging
import re
from urllib.parse import parse_qs, urlparse

from .config import Settings
from .state import State
from .tiles import RED, TILES

MAX_BYTES = 12 * 1024 * 1024
SUPPORTED = {
    "start_game",
    "start_kyoku",
    "tsumo",
    "dahai",
    "chi",
    "pon",
    "daiminkan",
    "ankan",
    "kakan",
    "reach",
    "reach_accepted",
    "dora",
    "hora",
    "ryukyoku",
    "end_kyoku",
    "end_game",
    "none",
}


def parse_link(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    domains = ("maj-soul.com", "mahjongsoul.com", "mahjongsoul.game.yo-star.com", "maj-soul.net")
    if parsed.scheme not in ("https", "http") or not any(
        host == d or host.endswith("." + d) for d in domains
    ):
        raise ValueError("请输入雀魂牌谱链接（需包含 paipu 参数）")
    raw = parse_qs(parsed.query).get("paipu", [""])[0].split("_")[0]
    if not re.fullmatch(r"[a-zA-Z0-9-]{20,100}", raw):
        raise ValueError("牌谱链接缺少有效 paipu 编号")
    return raw


async def fetch_majsoul(url: str, cfg: Settings) -> dict:
    from tensoul.downloader import MajsoulDownloadError, MajsoulLoginError

    from .majsoul import Downloader
    from .majsoul_versions import MajsoulProtocolError

    record_id = parse_link(url)
    if not cfg.majsoul_username or not cfg.majsoul_password:
        raise ValueError(
            "尚未配置完整的雀魂登录凭据。请在本机 .env 填写 XMAHJONG_MAJSOUL_USERNAME 和 "
            "XMAHJONG_MAJSOUL_PASSWORD 后重启服务；需使用 CN 原生账号密码，也可导入天凤6 JSON。"
        )
    downloader = Downloader()
    try:
        async with asyncio.timeout(180):
            await downloader.start()
            await downloader.login(cfg.majsoul_username, cfg.majsoul_password)
            return await downloader.download(record_id)
    except MajsoulProtocolError:
        raise
    except (MajsoulDownloadError, MajsoulLoginError) as exc:
        raise ValueError(
            f"雀魂拒绝下载（代码 {getattr(exc, 'code', 'login')}）。请配置 CN 账号或导入导出的 JSON。"
        ) from None
    except Exception as exc:  # noqa: BLE001 - upstream transport/parser errors are contained at the provider boundary
        logging.getLogger(__name__).warning("Majsoul provider failed: %s", type(exc).__name__)
        raise ValueError(
            "雀魂下载失败：网关或协议不可用。可导入导出的天凤6 JSON / MJAI；详情见 README。"
        ) from None
    finally:
        if getattr(downloader, "channel", None):
            try:
                await downloader.close()
            except Exception as exc:  # noqa: BLE001 - cleanup must not mask the original failure
                logging.getLogger(__name__).debug("Majsoul cleanup failed: %s", type(exc).__name__)


async def convert_tenhou(data: dict, cfg: Settings) -> list[dict]:
    if len(data.get("name", [])) != 4 or data.get("ratingc", "PF4") != "PF4":
        raise ValueError("仅支持四人日本麻将牌谱")
    display = data.get("rule", {}).get("disp", "")
    if "東" in display or "东" in display or "east" in display.lower():
        raise ValueError("当前只支持四人半庄，不支持东风战")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cfg.converter_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        raise ValueError("convlog 未安装。请先运行 scripts/build-engines.ps1，或直接导入 MJAI。") from None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(json.dumps(data).encode()), timeout=90)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ValueError("convlog 转换超时") from None
    if proc.returncode:
        raise ValueError("convlog 转换失败。请检查牌谱格式及转换器镜像是否已经构建。")
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def validate(events: list[dict]) -> list[dict]:
    if (
        not isinstance(events, list)
        or not 4 <= len(events) <= 50000
        or not isinstance(events[0], dict)
        or events[0].get("type") != "start_game"
    ):
        raise ValueError("MJAI 应包含 start_game 和完整事件流")
    state, in_round, has_round = State(), False, False
    if events[0].get("kyoku_first") == 4:
        raise ValueError("当前只支持半庄 MJAI，不支持东风战")
    for e in events:
        if not isinstance(e, dict) or e.get("type") not in SUPPORTED:
            raise ValueError("牌谱包含不支持的 MJAI 事件")
        if e["type"] not in ("start_game", "start_kyoku", "end_game", "end_kyoku", "none") and not in_round:
            raise ValueError("局内事件必须位于 start_kyoku 与 end_kyoku 之间")
        a = e.get("actor")
        if a is not None and (type(a) is not int or a not in range(4)):
            raise ValueError("actor 必须为 0–3")
        if e.get("target") is not None and e["target"] not in range(4):
            raise ValueError("target 必须为 0–3")
        for tile in [e[k] for k in ("pai", "dora_marker") if k in e] + e.get("consumed", []):
            if tile not in TILES and tile not in RED and tile != "?":
                raise ValueError(f"无效牌编码：{str(tile)[:20]}")
        if e["type"] == "start_kyoku":
            if in_round:
                raise ValueError("上一局缺少 end_kyoku")
            if len(e.get("tehais", [])) != 4 or any(len(h) != 13 for h in e["tehais"]):
                raise ValueError("起手必须为四家各 13 张牌")
            if e.get("bakaze") not in ("E", "S", "W") or e.get("kyoku") not in range(1, 5):
                raise ValueError("不支持的局数")
            if len(e.get("scores", [])) != 4:
                raise ValueError("必须提供四家分数")
            in_round, has_round = True, True
        if e["type"] == "end_kyoku":
            in_round = False
        try:
            state.apply(e)
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError(f"MJAI 事件字段不完整：{e['type']}") from exc
    if not has_round or in_round:
        raise ValueError("牌谱缺少完整对局")
    return events


async def parse_payload(raw: bytes, cfg: Settings) -> tuple[list[dict], dict | None]:
    if len(raw) > MAX_BYTES:
        raise ValueError("牌谱不能超过 12 MiB")
    text = raw.decode("utf-8-sig")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError:
            raise ValueError("请输入有效的 JSON 或 MJAI JSONL") from None
    original = data if isinstance(data, dict) and "log" in data else None
    if original:
        events = await convert_tenhou(original, cfg)
    elif isinstance(data, dict) and "events" in data:
        events = data["events"]
    elif isinstance(data, list):
        events = data
    else:
        raise ValueError("支持天凤6 JSON、MJAI 数组、JSONL 或 {events: [...]} 格式")
    return validate(events), original
