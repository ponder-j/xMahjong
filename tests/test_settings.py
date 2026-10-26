import importlib
import json

import httpx
from fastapi.testclient import TestClient
from xmahjong.app import create_app
from xmahjong.config import Settings, load_settings, save_llm_settings


def test_llm_profile_survives_reload_without_changing_engines(tmp_path):
    config = tmp_path / "config.local.json"
    config.write_text(
        json.dumps(
            {
                "data_dir": str(tmp_path / "data"),
                "mortal": {"version": "keep-engine"},
                "llm_model": "old-model",
            }
        ),
        encoding="utf-8",
    )
    settings = load_settings(config)
    settings.llm_base_url = "https://example.aliyuncs.com/compatible-mode/v1"
    settings.llm_api_key = "private-test-key"
    settings.llm_model = "qwen-test"
    settings.llm_extra_body = {"enable_thinking": False}
    save_llm_settings(settings)
    restored = load_settings(config)
    assert restored.llm_api_key == "private-test-key"
    assert restored.llm_model == "qwen-test"
    assert restored.llm_base_url == settings.llm_base_url
    assert restored.mortal.version == "keep-engine"
    assert json.loads(config.read_text())["llm_model"] == "old-model"
    assert not list((tmp_path / "data").glob(".llm-settings-*.tmp"))


def test_aliyun_save_is_persistent_and_preserves_existing_key(tmp_path):
    settings = Settings(data_dir=tmp_path, llm_api_key="private-test-key", llm_assistant_prefill="{")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/settings/llm",
            json={
                "base_url": "https://example.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-test",
                "thinking_compatibility": True,
            },
        )
        assert response.status_code == 200 and response.json()["persistent"] is True
        assert "private-test-key" not in response.text
        public = client.get("/api/health")
        assert "private-test-key" not in public.text
        assert public.json()["llm"]["persistent"] is True
        assert public.json()["llm"]["thinking_compatibility"] is False
        stored = json.loads((tmp_path / "llm-settings.json").read_text())
        assert stored["llm_api_key"] == "private-test-key"
        assert stored["llm_assistant_prefill"] == ""
        assert stored["llm_extra_body"]["enable_thinking"] is False


def test_failed_persistence_keeps_running_config(tmp_path, monkeypatch):
    module = importlib.import_module("xmahjong.app")

    def fail(_settings):
        raise OSError("simulated disk error")

    monkeypatch.setattr(module, "save_llm_settings", fail)
    settings = Settings(data_dir=tmp_path, llm_model="original-model", llm_api_key="original-key")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/settings/llm",
            json={"base_url": "https://example.com/v1", "model": "new-model", "api_key": "new-key"},
        )
        assert response.status_code == 500 and "new-key" not in response.text
        assert settings.llm_model == "original-model" and settings.llm_api_key == "original-key"


def test_invalid_llm_payload_never_echoes_key(tmp_path):
    secret = "private-test-key"
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        response = client.post("/api/settings/llm", json={"base_url": [], "model": [], "api_key": secret})
        assert response.status_code == 422 and secret not in response.text


def test_connection_check_requires_actual_chat_success(tmp_path, monkeypatch):
    module = importlib.import_module("xmahjong.app")

    async def fail_chat(_settings, _messages):
        response = httpx.Response(401, request=httpx.Request("POST", "https://example.com/chat/completions"))
        raise httpx.HTTPStatusError("unauthorized", request=response.request, response=response)

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, *_args, **_kwargs):
            return httpx.Response(200, json={"data": [{"id": "test-model"}]})

    monkeypatch.setattr(module.httpx, "AsyncClient", Client)
    monkeypatch.setattr(module.explainer, "completion", fail_chat)
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        result = client.post("/api/settings/llm/test").json()
        assert result["ok"] is False and result["status"] == 401
