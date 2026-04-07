from __future__ import annotations

from io import BytesIO

import httpx

from app.core.config import settings


class STTService:
    OPENAI_AUDIO_URL = "https://api.openai.com/v1/audio/transcriptions"

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str = "en",
    ) -> dict:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        files = {
            "file": (filename, BytesIO(audio_bytes), content_type),
        }
        data = {
            "model": settings.openai_stt_model,
            "language": language,
            "response_format": "verbose_json",
        }
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
        }
        timeout = httpx.Timeout(60.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self.OPENAI_AUDIO_URL,
                headers=headers,
                data=data,
                files=files,
            )

        if response.status_code != 200:
            raise RuntimeError(f"STT transcription failed: {response.text}")

        payload = response.json()
        return {
            "text": payload.get("text", ""),
            "language": payload.get("language", language),
            "duration": payload.get("duration"),
        }


_stt_service: STTService | None = None


def get_stt_service() -> STTService:
    global _stt_service
    if _stt_service is None:
        _stt_service = STTService()
    return _stt_service
