from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_api_keys(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    mapping: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            continue
        key, role = item.split(":", 1)
        key = key.strip()
        role = role.strip()
        if key and role:
            mapping[key] = role
    return mapping


def _parse_users(raw: str) -> dict[str, dict[str, str]]:
    if not raw:
        return {}
    mapping: dict[str, dict[str, str]] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3:
            continue
        username, password, role = parts
        if username and password and role:
            mapping[username] = {"password": password, "role": role}
    return mapping


class Settings(BaseModel):
    app_name: str = "AnyoneAI Interviewer API"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    auto_create_tables: bool = _parse_bool(os.getenv("AUTO_CREATE_TABLES", "true"))
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
    default_question_count: int = int(os.getenv("DEFAULT_QUESTION_COUNT", "5"))
    auth_enabled: bool = _parse_bool(os.getenv("AUTH_ENABLED", "true"))
    auth_header: str = os.getenv("AUTH_HEADER", "X-API-Key")
    api_keys: dict[str, str] = _parse_api_keys(os.getenv("API_KEYS", ""))
    jwt_secret: str = os.getenv("JWT_SECRET", "dev_secret_change_me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_access_minutes: int = int(os.getenv("JWT_ACCESS_MINUTES", "30"))
    jwt_refresh_days: int = int(os.getenv("JWT_REFRESH_DAYS", "7"))
    users: dict[str, dict[str, str]] = _parse_users(os.getenv("USER_CREDENTIALS", ""))
    candidate_token_days: int = int(os.getenv("CANDIDATE_TOKEN_DAYS", "7"))
    audio_upload_dir: str = os.getenv("AUDIO_UPLOAD_DIR", "/tmp/interview-audio")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    anthropic_temperature: float = float(os.getenv("ANTHROPIC_TEMPERATURE", "0.2"))
    max_context_qa: int = int(os.getenv("MAX_CONTEXT_QA", "4"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_stt_model: str = os.getenv("OPENAI_STT_MODEL", "whisper-1")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_default_voice_id: str = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    elevenlabs_default_voice_id_es: str = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID_ES", "")
    elevenlabs_default_voice_id_en: str = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID_EN", "")
    elevenlabs_model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    allowed_origins: list[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if origin.strip()
    ]
    allowed_origin_regex: str | None = os.getenv("ALLOWED_ORIGIN_REGEX") or None


settings = Settings()
