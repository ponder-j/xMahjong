"""Proxy-aware transport for tensoul 0.1.8; the record parser remains upstream.

Gateway discovery follows tensoul-py's MIT-licensed implementation.
https://github.com/ssttkkl/tensoul-py (Huang Wen Long)
"""

import asyncio
import hashlib
import hmac
import logging
import random
import time
from contextlib import suppress
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from ms import protocol_pb2 as pb
from ms.base import MSRPCChannel
from ms.rpc import Lobby, Route
from tensoul import MajsoulPaipuDownloader

from .majsoul_versions import MajsoulProtocolError, discover_versions, fetch_bytes


def check_response(response, stage: str) -> None:
    code = response.error.code
    if not code:
        return
    detail = {
        1004: "登录状态无效或缺少牌谱访问权限。请检查本机 CN 账号配置，或导入天凤6 JSON。",
        151: "客户端版本被拒绝；这不代表密码错误。请更新下载器或导入天凤6 JSON。",
        540: "牌谱请求受到限流。请稍后手动重试，或导入天凤6 JSON。",
    }.get(code, "请核对 CN 原生账号的登录方式，或导入天凤6 JSON。")
    raise MajsoulProtocolError(f"雀魂{stage}失败（代码 {code}）。{detail}")


def connection_request(route_id: str):
    request = pb.ReqRequestConnection(type=1, route_id=route_id, timestamp=int(time.time()))
    # String field 6 was added to the web protocol after ms-api 0.11.100.
    # Preserve it as an unknown protobuf field instead of changing site-packages.
    if "platform" in request.DESCRIPTOR.fields_by_name:
        request.platform = "Web"
    else:
        request.MergeFromString(b"\x32\x03Web")
    return request


class Downloader(MajsoulPaipuDownloader):
    async def _connect(self):
        # aiohttp defaults to ignoring HTTPS_PROXY; httpx honors local network settings.
        async with httpx.AsyncClient(timeout=20) as client:
            self.web_versions = await discover_versions(client)
            response = await client.get(self.MS_HOST + "/1/version.json")
            response.raise_for_status()
            self.version = response.json()["version"]
            self.version_to_force = self.version.replace(".w", "")
            response = await client.get(f"{self.MS_HOST}/1/v{self.version}/config.json")
            response.raise_for_status()
            config = response.json()
            network = config["ip"][0]
            routes = network.get("gateways") or network.get("region_urls")
            if not routes:
                raise ValueError("未识别的雀魂网关配置")
            if network.get("gateways"):
                for gateway in routes:
                    try:
                        response = await client.get(
                            gateway["url"].rstrip("/") + "/api/clientgate/routes",
                            params={"platform": "Web", "version": self.web_versions.package, "lang": "chs_t"},
                            timeout=8,
                        )
                        response.raise_for_status()
                        choices = response.json()["data"]["routes"]
                        choices.sort(key=lambda item: (item.get("state") != "idle", item.get("level", 999)))
                        route = choices[0]
                        self.route_id = route["id"]
                        self.endpoint = f"wss://{route['domain']}/gateway"
                        break
                    except (httpx.HTTPError, KeyError, IndexError):
                        continue
                else:
                    raise ValueError("雀魂网关均不可达")
            else:
                response = await client.get(
                    routes[0]["url"], params={"service": "ws-gateway", "protocol": "ws", "ssl": "true"}
                )
                response.raise_for_status()
                self.endpoint = f"wss://{random.choice(response.json()['servers'])}/gateway"
        host = urlparse(self.endpoint).hostname or ""
        if not any(host == d or host.endswith("." + d) for d in ("maj-soul.com", "maj-soul.net")):
            raise MajsoulProtocolError("雀魂网关域名不受支持，已停止登录。")
        self.channel = MSRPCChannel(self.endpoint)
        self.lobby = Lobby(self.channel)
        await self.channel.connect(self.MS_HOST)
        if getattr(self, "route_id", None):
            route = Route(self.channel)
            result = await asyncio.wait_for(
                route.request_connection(connection_request(self.route_id)), timeout=20
            )
            check_response(result, "连接握手")
            if result.result != 1:
                raise MajsoulProtocolError("雀魂网关尚未允许连接，请稍后重试。")
            check_response(await route.heartbeat(pb.ReqHeartbeat(platform=11)), "线路保活")
            self.keepalive_task = asyncio.create_task(self._keepalive(route))

    async def _keepalive(self, route):
        try:
            while True:
                await asyncio.sleep(15)
                result = await asyncio.wait_for(route.heartbeat(pb.ReqHeartbeat(platform=11)), timeout=10)
                check_response(result, "线路保活")
        except Exception as exc:  # noqa: BLE001 - foreground RPC has its own bounded timeout
            logging.getLogger(__name__).warning("Majsoul keepalive stopped: %s", type(exc).__name__)

    async def close(self):
        if task := getattr(self, "keepalive_task", None):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        async with asyncio.timeout(5):
            await super().close()

    async def login(self, username, password):
        versions = self.web_versions
        request = pb.ReqLogin(
            account=username,
            password=hmac.new(b"lailai", password.encode("utf-8"), hashlib.sha256).hexdigest(),
            random_key=str(uuid4()),
            gen_access_token=True,
            tag="cn",
            client_version_string=versions.client,
            currency_platforms=[1, 2, 5, 6, 8, 10, 11],
        )
        request.device.CopyFrom(
            pb.ClientDeviceInfo(
                platform="pc",
                hardware="pc",
                os="windows",
                os_version="win10",
                is_browser=True,
                software="Chrome",
                sale_platform="web",
                screen_type=1,
            )
        )
        request.client_version.package = versions.package
        request.client_version.resource = versions.resource
        result = await asyncio.wait_for(self.lobby.login(request), timeout=20)
        check_response(result, "登录")
        if not result.access_token or not result.account_id:
            raise MajsoulProtocolError("雀魂未返回有效登录凭据，请确认使用 CN 原生账号密码。")
        self.token = result.access_token
        check_response(
            await asyncio.wait_for(
                self.lobby.login_beat(pb.ReqLoginBeat(contract="DF2vkXCnfeXp4WoGrBGNcJBufZiMN3uP")),
                timeout=20,
            ),
            "登录确认",
        )
        check_response(
            await asyncio.wait_for(self.lobby.login_success(pb.ReqCommon()), timeout=20), "登录确认"
        )

    async def download(self, record_uuid: str):
        request = pb.ReqGameRecord(game_uuid=record_uuid, client_version_string=self.web_versions.client)
        record = await asyncio.wait_for(self.lobby.fetch_game_record(request), timeout=45)
        check_response(record, "下载牌谱")
        if not record.data and record.data_url:
            async with httpx.AsyncClient(timeout=20) as client:
                record.data = await fetch_bytes(client, record.data_url, limit=12 * 1024 * 1024)
        return self._handle_game_record(record)
