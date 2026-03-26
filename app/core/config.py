from pydantic import BaseModel
import os


class Settings(BaseModel):
    app_name: str = "AnyoneAI Interviewer API"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    default_question_count: int = int(os.getenv("DEFAULT_QUESTION_COUNT", "5"))


settings = Settings()
