from pydantic import BaseModel
import os


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


settings = Settings()
