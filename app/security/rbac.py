from collections.abc import Iterable
from fastapi import HTTPException, Request, status


def require_roles(*roles: str):
    allowed = set(roles)

    def _dependency(request: Request) -> str:
        role = getattr(request.state, "role", None)
        if not role:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        if role == "admin":
            return role
        if role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return role

    return _dependency
