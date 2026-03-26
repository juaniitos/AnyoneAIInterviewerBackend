from fastapi import FastAPI
from app.core.config import settings
from app.db.session import engine
from app.db.base import Base
from app.api.routes import roles, questions, candidates, interviews


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.include_router(roles.router)
    app.include_router(questions.router)
    app.include_router(candidates.router)
    app.include_router(interviews.router)

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    return app


app = create_app()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
