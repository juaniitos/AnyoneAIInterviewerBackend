from fastapi import HTTPException, Request, status
from app.core.config import settings
from app.security.jwt_tokens import decode_token

PUBLIC_PATH_PREFIXES = ("/docs", "/redoc")
PUBLIC_PATHS = {"/health", "/openapi.json", "/auth/login", "/auth/refresh"}


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


async def authenticate_request(request: Request) -> None:
    if not settings.auth_enabled or _is_public_path(request.url.path):
        return

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
        try:
            payload = decode_token(token)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        request.state.subject = payload.get("sub")
        request.state.role = payload.get("role")
        return

    api_key = request.headers.get(settings.auth_header)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    role = settings.api_keys.get(api_key)
    if not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    request.state.api_key = api_key
    request.state.role = role
