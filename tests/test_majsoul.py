import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ms import protocol_pb2 as pb
from xmahjong import majsoul, majsoul_versions
from xmahjong.config import Settings
from xmahjong.logs import fetch_majsoul
from xmahjong.majsoul_versions import MajsoulProtocolError, WebVersions

LINK = "https://game.maj-soul.com/1/?paipu=250211-5a117214-86b4-4143-bb62-6d383d0329e8_a123"


async def test_missing_credentials_do_not_make_anonymous_requests(monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(majsoul.Downloader, "start", start)
    with pytest.raises(ValueError, match="XMAHJONG_MAJSOUL_USERNAME"):
        await fetch_majsoul(LINK, Settings(majsoul_username="", majsoul_password=""))
    start.assert_not_called()


async def test_login_versions_hash_and_confirmation():
    downloader = majsoul.Downloader()
    downloader.web_versions = WebVersions(package="4.1.2", resource="0.16.300")
    downloader.lobby = SimpleNamespace(
        login=AsyncMock(return_value=pb.ResLogin(account_id=123, access_token="test-session")),
        login_beat=AsyncMock(return_value=pb.ResCommon()),
        login_success=AsyncMock(return_value=pb.ResCommon()),
    )
    await downloader.login("test-account", "test-password")
    request = downloader.lobby.login.call_args.args[0]
    assert request.account == "test-account"
    assert request.password == hmac.new(b"lailai", b"test-password", hashlib.sha256).hexdigest()
    assert request.client_version.package == "4.1.2"
    assert request.client_version.resource == "0.16.300"
    assert request.client_version_string == "WebGL_2022-0.16.300"
    assert request.device.is_browser and request.tag == "cn"
    downloader.lobby.login_beat.assert_awaited_once()
    downloader.lobby.login_success.assert_awaited_once()


@pytest.mark.parametrize("code,reason", [(1004, "登录状态"), (151, "版本"), (540, "限流")])
async def test_upstream_errors_are_specific_and_do_not_include_response_bodies(code, reason):
    response = pb.ResLogin(error=pb.Error(code=code, str_params=["test-private-value"]))
    with pytest.raises(MajsoulProtocolError, match=reason) as caught:
        majsoul.check_response(response, "登录")
    assert str(code) in str(caught.value)
    assert "test-private-value" not in str(caught.value)


def test_handshake_has_web_platform_and_seconds_timestamp():
    request = majsoul.connection_request("cn-test")
    assert request.type == 1
    assert request.route_id == "cn-test"
    assert request.timestamp < 10_000_000_000
    assert b"\x32\x03Web" in request.SerializeToString()


def test_version_metadata_distinguishes_package_from_resource(monkeypatch):
    assert majsoul_versions.package_version('productVersion: "4.1.2"') == "4.1.2"
    with pytest.raises(MajsoulProtocolError):
        majsoul_versions.package_version('productVersion: "4.1.2"; productVersion: "4.1.3"')
    catalog = {
        "assetInfos": [{"assetPath": "MyAssets/Docs_Version/version.json", "ownerBundleIndex": 0}],
        "bundleInfos": [{"name": "docs_version_123.majset"}],
    }
    obj = SimpleNamespace(type=SimpleNamespace(name="MonoBehaviour"), parse_as_dict=lambda: catalog)
    monkeypatch.setattr(majsoul_versions, "_bundle", lambda data: SimpleNamespace(objects=[obj]))
    assert majsoul_versions.locate_version_bundle(b"test") == "docs_version_123.majset"
    catalog["bundleInfos"][0]["name"] = "../../bad.majset"
    with pytest.raises(MajsoulProtocolError):
        majsoul_versions.locate_version_bundle(b"test")


async def test_protocol_error_survives_provider_boundary_and_cleanup(monkeypatch):
    close = AsyncMock()
    monkeypatch.setattr(majsoul.Downloader, "start", AsyncMock())
    monkeypatch.setattr(majsoul.Downloader, "channel", object(), raising=False)
    monkeypatch.setattr(majsoul.Downloader, "close", close)
    monkeypatch.setattr(
        majsoul.Downloader, "login", AsyncMock(side_effect=MajsoulProtocolError("登录失败（代码 151）：版本"))
    )
    with pytest.raises(ValueError, match="151"):
        await fetch_majsoul(LINK, Settings(majsoul_username="test", majsoul_password="test"))
    close.assert_awaited_once()
