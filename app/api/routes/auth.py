from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.core.config import settings
from app import models, schemas
from app.security.jwt_tokens import create_access_token, create_refresh_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.AdminUser).filter(models.AdminUser.email == payload.email).first()
    if db_user:
        if not pwd_context.verify(payload.password, db_user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        access = create_access_token(payload.email, "admin")
        refresh = create_refresh_token(payload.email, "admin")
        return TokenResponse(access_token=access, refresh_token=refresh)

    env_user = settings.users.get(payload.email)
    if not env_user or env_user["password"] != payload.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access = create_access_token(payload.email, env_user["role"])
    refresh = create_refresh_token(payload.email, env_user["role"])
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest):
    try:
        decoded = decode_token(payload.refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    subject = decoded.get("sub")
    role = decoded.get("role")
    if not subject or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    access = create_access_token(subject, role)
    refresh_token = create_refresh_token(subject, role)
    return TokenResponse(access_token=access, refresh_token=refresh_token)


@router.post("/signup", response_model=schemas.AdminUserRead, status_code=status.HTTP_201_CREATED)
def signup(payload: schemas.AdminUserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.AdminUser).filter(models.AdminUser.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    password_hash = pwd_context.hash(payload.password)
    admin_user = models.AdminUser(
        email=payload.email,
        password_hash=password_hash,
        name=payload.name,
        is_active=True,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)
    return admin_user
