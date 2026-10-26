import asyncio
import hashlib
import json
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import explainer
from .analysis import analyze
from .config import LLM_FIELDS, ROOT, Settings, load_settings, save_llm_settings
from .evidence import discard_evidence
from .logs import MAX_BYTES, fetch_majsoul, parse_payload
from .state import decisions
from .storage import Storage


class LinkImport(BaseModel):
    url: str = Field(min_length=20, max_length=2000)


class LLMSettings(BaseModel):
    base_url: str = Field(max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=1000)
    thinking_compatibility: bool = False


class Followup(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=10)


class Counterfactual(BaseModel):
    tile: str = Field(min_length=1, max_length=4)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    storage = Storage(cfg.data_dir)
    app = FastAPI(title="XMahjong", version="0.1.0", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    app.state.settings, app.state.storage = cfg, storage
    inference_limit, llm_limit = asyncio.Semaphore(1), asyncio.Semaphore(1)

    @app.middleware("http")
    async def local_guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "仅接受同源请求"}, status_code=403)
        if (
            request.headers.get("content-length", "0").isdigit()
            and int(request.headers.get("content-length", "0")) > MAX_BYTES + 65536
        ):
            return JSONResponse({"detail": "请求过大"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({"detail": str(exc)[:300]}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing(_request, _exc):
        return JSONResponse({"detail": "牌谱或局面不存在"}, status_code=404)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path == "/api/settings/llm":
            return JSONResponse(
                {
                    "detail": [
                        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                        for error in exc.errors()
                    ]
                },
                status_code=422,
            )
        return await request_validation_exception_handler(request, exc)

    def replay(replay_id: str):
        return storage.get(replay_id)

    @lru_cache(maxsize=24)
    def decision_list(replay_id: str, actor: int):
        if actor not in range(4):
            raise ValueError("actor 必须为 0–3")
        return decisions(replay(replay_id)["events"], actor)

    def decision_at(replay_id: str, actor: int, decision_id: int):
        return next((d for d in decision_list(replay_id, actor) if d["id"] == decision_id), None)

    async def get_analysis(replay_id: str, actor: int, decision_id: int, refresh: bool = False):
        decision = decision_at(replay_id, actor, decision_id)
        if decision is None:
            raise KeyError(decision_id)
        # Include every engine setting and evidence version in cache identity; never use an old weight's scores.
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "schema": 2,
                    "mortal": cfg.mortal.model_dump(),
                    "akochan": cfg.akochan.model_dump(),
                    "temperature": cfg.temperature,
                    "top_k": cfg.top_k,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:24]
        key = f"{replay_id}:{actor}:{decision_id}:{fingerprint}"
        async with inference_limit:
            cached = storage.cached(key) if not refresh else None
            if cached:
                return cached
            report = await analyze(replay(replay_id)["events"], decision, cfg)
            # Failure reports should retry after installation or a transient runtime failure.
            if all(e["status"] not in ("error", "timeout") for e in report["engines"]):
                storage.cache(key, report)
            return report

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "engines": {
                name: {"configured": bool(getattr(cfg, name).command), "version": getattr(cfg, name).version}
                for name in ("mortal", "akochan")
            },
            "llm": {
                "base_url": cfg.llm_base_url,
                "model": cfg.llm_model,
                "has_api_key": bool(cfg.llm_api_key),
                "thinking_compatibility": bool(cfg.llm_assistant_prefill),
                "persistent": (cfg.data_dir / "llm-settings.json").exists(),
            },
        }

    @app.post("/api/settings/llm")
    async def llm_settings(body: LLMSettings):
        from urllib.parse import urlparse

        url = urlparse(body.base_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError("base_url 必须是 http(s) URL，不可包含认证信息")
        changes = {
            "llm_base_url": body.base_url.rstrip("/"),
            "llm_model": body.model,
            "llm_assistant_prefill": "{" if body.thinking_compatibility else "",
        }
        extra = dict(cfg.llm_extra_body)
        if url.hostname.endswith(".aliyuncs.com"):
            # Qwen JSON output uses non-thinking mode, not llama.cpp assistant prefill.
            changes["llm_assistant_prefill"] = ""
            extra["enable_thinking"] = False
        elif (urlparse(cfg.llm_base_url).hostname or "").endswith(".aliyuncs.com"):
            extra.pop("enable_thinking", None)
        changes["llm_extra_body"] = extra
        if body.api_key is not None:
            changes["llm_api_key"] = body.api_key
        updated = cfg.model_copy(update=changes)
        try:
            save_llm_settings(updated)
        except OSError:
            raise HTTPException(
                status_code=500, detail="本地配置保存失败，请检查 data 目录的写入权限"
            ) from None
        for field in LLM_FIELDS:
            setattr(cfg, field, getattr(updated, field))
        return {"saved": True, "persistent": True, "scope": "已保存到本机，重启服务后自动恢复。"}

    @app.post("/api/settings/llm/test")
    async def llm_test():
        headers = {"Authorization": "Bearer " + cfg.llm_api_key} if cfg.llm_api_key else {}
        models = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(cfg.llm_base_url + "/models", headers=headers)
                if res.is_success:
                    models = [m["id"] for m in res.json().get("data", [])]
        except (httpx.HTTPError, ValueError, KeyError):
            pass  # Some compatible providers offer chat but no model-list endpoint.
        try:
            probe = cfg.model_copy(update={"llm_max_tokens": 96, "llm_timeout": 30})
            content = await explainer.completion(
                probe,
                [
                    {"role": "system", "content": "Only return a JSON object."},
                    {"role": "user", "content": "Return the JSON object with ok equal to true."},
                ],
            )
            if json.loads(content).get("ok") is not True:
                raise ValueError("unexpected probe output")
            return {
                "ok": True,
                "model": cfg.llm_model,
                "models": models or [cfg.llm_model],
                "verified": "chat_completions",
                "message": "当前模型实际生成测试通过。",
            }
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = {
                401: "密钥无效或与当前端点不匹配",
                403: "密钥没有当前模型的访问权限",
                404: "端点或模型不存在",
                429: "调用受到限制，请检查额度与频率",
                400: "生成请求参数不兼容，请检查模型及兼容模式",
            }.get(status, "模型服务返回错误，请稍后重试")
            return {"ok": False, "status": status, "message": message}
        except (httpx.HTTPError, ValueError, KeyError):
            return {"ok": False, "message": "实际生成测试失败或输出被截断，请检查模型配置与网络"}

    @app.get("/api/replays")
    async def list_replays():
        return storage.list()

    @app.post("/api/replays/import")
    async def import_file(file: Annotated[UploadFile, File()]):
        raw = await file.read(MAX_BYTES + 1)
        events, original = await parse_payload(raw, cfg)
        return {"id": storage.save(events, original, file.filename or "本地导入"), "event_count": len(events)}

    @app.post("/api/replays/link")
    async def import_link(body: LinkImport):
        data = await fetch_majsoul(body.url, cfg)
        events, original = await parse_payload(json.dumps(data).encode(), cfg)
        return {"id": storage.save(events, original, body.url), "event_count": len(events)}

    @app.post("/api/replays/example")
    async def load_example():
        raw = (ROOT / "tests" / "fixtures" / "example.mjai.jsonl").read_bytes()
        events, original = await parse_payload(raw, cfg)
        return {
            "id": storage.save(events, original, "上游真实天凤测试牌谱（非雀魂验收）"),
            "event_count": len(events),
        }

    @app.get("/api/replays/{replay_id}/decisions")
    async def get_decisions(replay_id: str, actor: int = 0):
        data = replay(replay_id)
        items = decision_list(replay_id, actor)
        return {
            "id": replay_id,
            "title": data["title"],
            "source": data["source"],
            "names": data["events"][0].get("names", []),
            "actor": actor,
            "decisions": [
                {
                    "id": d["id"],
                    "kind": d["kind"],
                    "bakaze": d["state"]["bakaze"],
                    "kyoku": d["state"]["kyoku"],
                    "honba": d["state"]["honba"],
                    "turn": d["state"]["turn"],
                    "trigger": d["state"]["trigger"],
                    "actual": d["actual"],
                }
                for d in items
            ],
        }

    @app.get("/api/replays/{replay_id}/decisions/{decision_id}")
    async def get_decision(replay_id: str, decision_id: int, actor: int = 0):
        d = decision_at(replay_id, actor, decision_id)
        if d is None:
            raise KeyError(decision_id)
        return d

    @app.get("/api/replays/{replay_id}/mjai")
    async def export(replay_id: str):
        # Explicit export includes full original replay; never sent to LLM/inference.
        return Response(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in replay(replay_id)["events"]),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f'attachment; filename="{replay_id}.jsonl"'},
        )

    @app.post("/api/replays/{replay_id}/decisions/{decision_id}/analyze")
    async def analyze_decision(replay_id: str, decision_id: int, actor: int = 0, refresh: bool = False):
        return await get_analysis(replay_id, actor, decision_id, refresh)

    @app.post("/api/replays/{replay_id}/decisions/{decision_id}/explain")
    async def explain_decision(replay_id: str, decision_id: int, actor: int = 0):
        report = await get_analysis(replay_id, actor, decision_id)
        async with llm_limit:
            return await explainer.explain(report, cfg)

    @app.post("/api/replays/{replay_id}/decisions/{decision_id}/chat")
    async def followup(replay_id: str, decision_id: int, body: Followup, actor: int = 0):
        report = await get_analysis(replay_id, actor, decision_id)
        async with llm_limit:
            return await explainer.chat(report, body.question, body.history, cfg)

    @app.post("/api/replays/{replay_id}/decisions/{decision_id}/counterfactual")
    async def counterfactual(replay_id: str, decision_id: int, body: Counterfactual, actor: int = 0):
        d = decision_at(replay_id, actor, decision_id)
        if d is None:
            raise KeyError(decision_id)
        evidence = await asyncio.to_thread(
            discard_evidence, d["state"], {"type": "dahai", "actor": actor, "pai": body.tile}
        )
        return {
            "mode": "one_step_discard",
            "action": body.tile,
            "evidence": evidence,
            "notice": "仅重算合法弃牌后的即时证据；不沿用原牌谱未来结果，不伪造模型重推理。",
        }

    app.mount("/assets", StaticFiles(directory=ROOT / "frontend"), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "frontend" / "index.html")

    @app.get("/docs")
    async def docs():
        return FileResponse(ROOT / "frontend" / "api.html")

    return app


app = create_app()
