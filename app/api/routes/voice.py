from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.public import _resolve_candidate_session
from app.core.rate_limit import limiter
from app.services.stt import STTService, get_stt_service
from app.services.tts import TTSService, get_tts_service
from app.services.tts.exceptions import ElevenLabsError, TTSValidationError
from app.services.tts.schemas import TTSRequest, VoicesResponse

router = APIRouter(prefix="/public/voice", tags=["public-voice"])


@router.post("/transcribe")
@limiter.limit("10/minute")
async def transcribe_candidate_audio(
    request: Request,
    interview_id: str = Query(...),
    token: str = Query(...),
    question_id: str = Form(...),
    language: str = Form("en"),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    stt_service: STTService = Depends(get_stt_service),
):
    session = _resolve_candidate_session(db, interview_id, token)
    if session.current_question_id and question_id != session.current_question_id:
        raise HTTPException(status_code=409, detail="Audio does not match the current interview question")

    audio_bytes = await audio.read()
    result = await stt_service.transcribe(
        audio_bytes=audio_bytes,
        filename=audio.filename or "audio.webm",
        content_type=audio.content_type or "audio/webm",
        language=language,
    )
    return {
        "question_id": question_id,
        "transcript": result["text"],
        "language": result["language"],
        "audio_duration_sec": result["duration"],
    }


@router.post("/synthesize")
@limiter.limit("15/minute")
async def synthesize_question_audio(
    request: Request,
    interview_id: str = Query(...),
    token: str = Query(...),
    text: str = Form(...),
    voice_id: str | None = Form(None),
    language: str = Form("en"),
    db: Session = Depends(get_db),
    tts_service: TTSService = Depends(get_tts_service),
):
    _resolve_candidate_session(db, interview_id, token)

    request = TTSRequest(
        text=text,
        voice_id=voice_id,
        language=language,
        session_id=interview_id,
    )

    try:
        async def audio_generator():
            async for chunk in tts_service.synthesize(request):
                yield chunk

        return StreamingResponse(audio_generator(), media_type="audio/mpeg")
    except TTSValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ElevenLabsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/voices", response_model=VoicesResponse)
@limiter.limit("30/minute")
async def list_tts_voices(
    request: Request,
    tts_service: TTSService = Depends(get_tts_service),
):
    try:
        return await tts_service.list_voices()
    except ElevenLabsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
