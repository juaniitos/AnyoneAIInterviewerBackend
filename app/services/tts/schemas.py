from pydantic import BaseModel, Field


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: str | None = None
    language: str = "en"
    session_id: str = "standalone"
    stability: float = Field(0.4, ge=0.0, le=1.0)
    similarity_boost: float = Field(0.88, ge=0.0, le=1.0)
    style: float = Field(0.28, ge=0.0, le=1.0)
    speed: float = Field(0.97, ge=0.85, le=1.15)
    use_speaker_boost: bool = True


class VoiceInfo(BaseModel):
    voice_id: str
    name: str
    preview_url: str | None = None
    labels: dict = {}


class VoicesResponse(BaseModel):
    voices: list[VoiceInfo]
