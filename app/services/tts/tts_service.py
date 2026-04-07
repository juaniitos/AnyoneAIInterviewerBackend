import time
from typing import AsyncGenerator

from .elevenlabs_provider import ElevenLabsProvider
from .schemas import TTSRequest, VoiceInfo, VoicesResponse

_VOICES_CACHE: dict = {"voices": None, "timestamp": 0.0}
_CACHE_TTL = 3600.0


class TTSService:
    def __init__(self, provider: ElevenLabsProvider) -> None:
        self.provider = provider

    def _voice_for_request(self, request: TTSRequest) -> str:
        if request.voice_id:
            return request.voice_id
        if (request.language or "en").lower().startswith("es") and self.provider.default_voice_id_es:
            return self.provider.default_voice_id_es
        if (request.language or "en").lower().startswith("en") and self.provider.default_voice_id_en:
            return self.provider.default_voice_id_en
        return self.provider.default_voice_id

    def _settings_for_request(self, request: TTSRequest) -> dict[str, float | bool]:
        stability = request.stability
        similarity_boost = request.similarity_boost
        style = request.style
        speed = request.speed

        if (request.language or "en").lower().startswith("es"):
            stability = max(stability, 0.4)
            similarity_boost = max(similarity_boost, 0.88)
            style = max(style, 0.28)
            speed = min(speed, 0.97)

        return {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "speed": speed,
            "use_speaker_boost": request.use_speaker_boost,
        }

    async def synthesize(self, request: TTSRequest) -> AsyncGenerator[bytes, None]:
        cleaned_text = self.provider._preprocess_text(request.text, language=request.language)
        voice_id = self._voice_for_request(request)
        voice_settings = self._settings_for_request(request)
        async for chunk in self.provider.stream_audio(
            text=cleaned_text,
            voice_id=voice_id,
            stability=voice_settings["stability"],
            similarity_boost=voice_settings["similarity_boost"],
            style=voice_settings["style"],
            speed=voice_settings["speed"],
            use_speaker_boost=voice_settings["use_speaker_boost"],
        ):
            yield chunk

    async def list_voices(self) -> VoicesResponse:
        now = time.monotonic()
        if _VOICES_CACHE["voices"] is not None and (now - _VOICES_CACHE["timestamp"]) < _CACHE_TTL:
            return _VOICES_CACHE["voices"]

        raw_voices = await self.provider.list_voices()
        result = VoicesResponse(
            voices=[
                VoiceInfo(
                    voice_id=voice.get("voice_id", ""),
                    name=voice.get("name", ""),
                    preview_url=voice.get("preview_url"),
                    labels=voice.get("labels", {}),
                )
                for voice in raw_voices
            ]
        )
        _VOICES_CACHE["voices"] = result
        _VOICES_CACHE["timestamp"] = now
        return result


_tts_service: TTSService | None = None


def get_tts_service() -> TTSService:
    global _tts_service
    if _tts_service is None:
        from app.core.config import settings

        provider = ElevenLabsProvider(
            api_key=settings.elevenlabs_api_key,
            default_voice_id=settings.elevenlabs_default_voice_id,
            default_voice_id_es=settings.elevenlabs_default_voice_id_es or settings.elevenlabs_default_voice_id,
            default_voice_id_en=settings.elevenlabs_default_voice_id_en or settings.elevenlabs_default_voice_id,
            model_id=settings.elevenlabs_model_id,
        )
        _tts_service = TTSService(provider)
    return _tts_service
