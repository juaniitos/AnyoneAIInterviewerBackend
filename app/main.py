from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.db.session import engine
from app.db.base import Base
from app.api.routes import roles, questions, candidates, interviews, admin_interviews, auth
from app.security.auth import authenticate_request


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    @app.middleware("http")
    async def auth_middleware(request, call_next):
        try:
            await authenticate_request(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    app.include_router(roles.router)
    app.include_router(questions.router)
    app.include_router(candidates.router)
    app.include_router(interviews.router)
    app.include_router(admin_interviews.router)
    app.include_router(auth.router)

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    return app


app = create_app()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
