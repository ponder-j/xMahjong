"""Read version metadata from the official Unity web client without running its code."""

import asyncio
import json
import re
import warnings
from dataclasses import dataclass

import httpx

HOST = "https://game.maj-soul.com"
ASSETS = HOST + "/assetbundles/ASTC/"
VERSION_ASSET = "myassets/docs_version/version.json"
VERSION_PATTERN = r"\d{1,3}(?:\.\d{1,5}){2,3}"
METADATA_LIMIT = 4 * 1024 * 1024


class MajsoulProtocolError(ValueError):
    """A safe, user-facing protocol error; never includes an upstream response body."""


@dataclass(frozen=True)
class WebVersions:
    package: str
    resource: str

    @property
    def client(self) -> str:
        return f"WebGL_2022-{self.resource}"


async def fetch_bytes(client: httpx.AsyncClient, url: str, limit: int = METADATA_LIMIT) -> bytes:
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > limit:
                raise MajsoulProtocolError("雀魂返回的数据超过大小限制，已停止下载。")
    return bytes(content)


def package_version(page: str) -> str:
    matches = re.findall(rf"""\bproductVersion\s*:\s*["']({VERSION_PATTERN})["']""", page)
    if not matches or len(set(matches)) != 1:
        raise MajsoulProtocolError("无法识别雀魂当前程序版本，请更新下载器或导入 JSON。")
    return matches[0]


def _bundle(data: bytes):
    import UnityPy

    if not data.startswith(b"UnityFS\0") or len(data) > METADATA_LIMIT:
        raise MajsoulProtocolError("雀魂版本元数据格式不受支持，请更新下载器或导入 JSON。")
    # The official bundles omit the engine version in their header.
    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.0f1"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return UnityPy.load(data)


def locate_version_bundle(data: bytes) -> str:
    names = set()
    for obj in _bundle(data).objects:
        if obj.type.name != "MonoBehaviour":
            continue
        catalog = obj.parse_as_dict()
        for asset in catalog.get("assetInfos", []):
            if asset.get("assetPath", "").replace("\\", "/").lower() == VERSION_ASSET:
                index = asset.get("ownerBundleIndex")
                bundles = catalog.get("bundleInfos", [])
                if type(index) is int and 0 <= index < len(bundles):
                    names.add(bundles[index].get("name", ""))
    if len(names) != 1:
        raise MajsoulProtocolError("雀魂资源清单已变化，无法定位版本元数据。请更新下载器或导入 JSON。")
    name = names.pop()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,150}\.majset", name):
        raise MajsoulProtocolError("雀魂资源清单含有无效的版本文件名。")
    return name


def resource_version(data: bytes) -> str:
    versions = set()
    for path, obj in _bundle(data).container.items():
        if path.replace("\\", "/").lower() != VERSION_ASSET:
            continue
        document = json.loads(obj.deref_parse_as_object().m_Script)
        version = document.get("version", "")
        if (
            document.get("platform") == "WebGL"
            and isinstance(version, str)
            and re.fullmatch(VERSION_PATTERN, version)
        ):
            versions.add(version)
    if len(versions) != 1:
        raise MajsoulProtocolError("无法识别雀魂当前资源版本，请更新下载器或导入 JSON。")
    return versions.pop()


async def discover_versions(client: httpx.AsyncClient) -> WebVersions:
    page, catalog = await asyncio.gather(
        fetch_bytes(client, HOST + "/1/"),
        fetch_bytes(client, ASSETS + "bundle_info_so.majset"),
    )
    package = package_version(page.decode("utf-8"))
    name = await asyncio.to_thread(locate_version_bundle, catalog)
    resource = await fetch_bytes(client, ASSETS + name)
    return WebVersions(package, await asyncio.to_thread(resource_version, resource))
