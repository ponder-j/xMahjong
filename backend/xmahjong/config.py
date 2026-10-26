import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class EngineConfig(BaseModel):
    command: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    version: str = "unconfigured"
    weight_sha256: str | None = None
    timeout: float = Field(default=120, gt=0, le=600)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XMAHJONG_", env_file=ROOT / ".env", extra="ignore")
    data_dir: Path = ROOT / "data"
    converter_command: list[str] = ["docker", "run", "--rm", "-i", "xmahjong/convlog:local"]
    mortal: EngineConfig = EngineConfig()
    akochan: EngineConfig = EngineConfig()
    temperature: float = Field(default=0.1, gt=0, le=10)
    top_k: int = Field(default=5, ge=1, le=30)
    llm_base_url: str = "http://127.0.0.1:18080/v1"
    llm_api_key: str = ""
    llm_model: str = "local-qwen"
    llm_timeout: float = 180
    llm_max_tokens: int = 3000
    llm_extra_body: dict = Field(default_factory=dict)
    llm_assistant_prefill: str = ""
    majsoul_username: str = Field(default="", repr=False)
    majsoul_password: str = Field(default="", repr=False)


def load_settings(config_file: Path | None = None) -> Settings:
    path = config_file or ROOT / "config.local.json"
    settings = Settings(**json.loads(path.read_text(encoding="utf-8-sig"))) if path.exists() else Settings()
    saved = settings.data_dir / "llm-settings.json"
    if saved.exists():
        values = json.loads(saved.read_text(encoding="utf-8"))
        settings = settings.model_copy(update=validate_llm_values(values))
    return settings


LLM_FIELDS = ("llm_base_url", "llm_model", "llm_api_key", "llm_assistant_prefill", "llm_extra_body")


def validate_llm_values(values: dict) -> dict:
    # Ignore unrelated fields so a saved LLM profile cannot change engine commands.
    checked = Settings(**{key: values[key] for key in LLM_FIELDS if key in values})
    return {key: getattr(checked, key) for key in LLM_FIELDS if key in values}


def save_llm_settings(settings: Settings) -> Path:
    """Keep URL, model and key together in one atomic, local-only profile."""
    directory = settings.data_dir
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "llm-settings.json"
    values = {key: getattr(settings, key) for key in LLM_FIELDS}
    descriptor, temporary = tempfile.mkstemp(prefix=".llm-settings-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(values, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
