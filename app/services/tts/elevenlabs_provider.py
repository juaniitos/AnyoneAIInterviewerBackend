import re
from typing import AsyncGenerator

import httpx

from .exceptions import ElevenLabsError, TTSValidationError


class ElevenLabsProvider:
    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(
        self,
        api_key: str,
        default_voice_id: str,
        model_id: str,
        default_voice_id_es: str | None = None,
        default_voice_id_en: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.default_voice_id = default_voice_id
        self.default_voice_id_es = default_voice_id_es or default_voice_id
        self.default_voice_id_en = default_voice_id_en or default_voice_id
        self.model_id = model_id

    def _looks_like_question(self, text: str, language: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            return False
        if cleaned.endswith("?"):
            return True
        normalized = cleaned.lower()
        if language == "es":
            return normalized.startswith((
                "como ",
                "que ",
                "cual ",
                "cuales ",
                "por que ",
                "de que ",
                "puedes ",
                "podrias ",
                "cuentame ",
                "describe ",
                "hablame ",
            ))
        return normalized.startswith((
            "how ",
            "what ",
            "which ",
            "why ",
            "when ",
            "where ",
            "can you ",
            "could you ",
            "tell me ",
            "describe ",
        ))

    def _postprocess_for_speech(self, text: str, language: str) -> str:
        cleaned = text.replace("/", ", ")
        cleaned = re.sub(r"\s*[:;]\s*", ". ", cleaned)
        cleaned = re.sub(r"\s*[—-]\s*", ", ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if language == "es":
            cleaned = re.sub(r"\bAI\b", "inteligencia artificial", cleaned)
            cleaned = re.sub(r"\bIA\b", "inteligencia artificial", cleaned)
            if self._looks_like_question(cleaned, language):
                core = cleaned.strip().strip("¿?")
                if not core.endswith("?"):
                    core = f"{core}?"
                cleaned = f"¿{core}"
        else:
            cleaned = re.sub(r"\bIA\b", "AI", cleaned)
            if self._looks_like_question(cleaned, language) and not cleaned.endswith("?"):
                cleaned = f"{cleaned}?"

        if cleaned and cleaned[-1] not in ".!?":
            cleaned = f"{cleaned}."

        return cleaned

    def _preprocess_text(self, text: str, language: str = "en") -> str:
        cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"_{1,3}(.*?)_{1,3}", r"\1", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^>\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            raise TTSValidationError("Text is empty after preprocessing.")
        return self._postprocess_for_speech(cleaned, language)

    async def stream_audio(
        self,
        text: str,
        voice_id: str,
        stability: float,
        similarity_boost: float,
        style: float,
        speed: float,
        use_speaker_boost: bool,
    ) -> AsyncGenerator[bytes, None]:
        url = f"{self.BASE_URL}/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "speed": speed,
                "use_speaker_boost": use_speaker_boost,
            },
        }
        timeout = httpx.Timeout(30.0, connect=5.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise ElevenLabsError(
                        message=f"ElevenLabs API error: {error_body.decode()}",
                        status_code=response.status_code,
                    )
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk

    async def list_voices(self) -> list[dict]:
        url = f"{self.BASE_URL}/voices"
        headers = {"xi-api-key": self.api_key}
        timeout = httpx.Timeout(10.0, connect=5.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            raise ElevenLabsError(
                message=f"Failed to fetch voices: {response.text}",
                status_code=response.status_code,
            )

        return response.json().get("voices", [])
