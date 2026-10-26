import json

from fastapi.testclient import TestClient
from xmahjong.app import create_app
from xmahjong.config import Settings


def test_offline_end_to_end_api(events, tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        result = client.post(
            "/api/replays/import", files={"file": ("replay.json", json.dumps(events).encode())}
        )
        assert result.status_code == 200
        replay = result.json()["id"]
        listing = client.get(f"/api/replays/{replay}/decisions").json()
        first = listing["decisions"][0]["id"]
        snapshot = client.get(f"/api/replays/{replay}/decisions/{first}").json()
        assert "hands" not in snapshot["state"]
        report = client.post(f"/api/replays/{replay}/decisions/{first}/analyze").json()
        assert report["disagreement"]["level"] == "unknown"
        assert all(e["status"] == "unconfigured" for e in report["engines"])
        assert report["explanation"]["source"] == "computed"
        assert len(report["candidates"]) > 1
        legal = report["candidates"][0]["moves"][-1]["pai"]
        cf = client.post(f"/api/replays/{replay}/decisions/{first}/counterfactual", json={"tile": legal})
        assert cf.status_code == 200 and cf.json()["mode"] == "one_step_discard"
        assert (
            client.post(
                f"/api/replays/{replay}/decisions/{first}/counterfactual", json={"tile": "garb"}
            ).status_code
            == 422
        )
        assert client.get(f"/api/replays/{replay}/decisions/99999").status_code == 404
        assert client.get(f"/api/replays/{replay}/decisions?actor=4").status_code == 422
        assert client.get("/").status_code == 200
        assert client.get("/assets/app.js").status_code == 200


def test_secrets_and_cross_origin(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, llm_api_key="secret-test-value"))
    with TestClient(app) as client:
        assert "secret-test-value" not in client.get("/api/health").text
        assert (
            client.post(
                "/api/settings/llm",
                headers={"Origin": "https://untrusted.example"},
                json={"base_url": "http://localhost/v1", "model": "x"},
            ).status_code
            == 403
        )
        response = client.post(
            "/api/settings/llm",
            json={"base_url": "http://localhost/v1", "model": "x", "api_key": "new-secret"},
        )
        assert response.status_code == 200 and "new-secret" not in response.text


def test_invalid_imports(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        for payload in [b"bad json", b"{}", b"[]", b'{"events": {}}']:
            assert (
                client.post("/api/replays/import", files={"file": ("bad.json", payload)}).status_code == 422
            )
        assert (
            client.post(
                "/api/replays/link", json={"url": "https://example.com/?paipu=12345678901234567890"}
            ).status_code
            == 422
        )
