import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, WebSocket
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.db.session import SessionLocal
from app.core.config import settings
from app.security.auth import get_websocket_role
from app.services.interview_state_service import (
    build_semantic_question_plan,
    clarify_current_question,
    get_interview_language,
    initialize_interview_graph,
    set_interview_language,
    skip_current_question,
    submit_interview_answer,
)
from app.services.stt import get_stt_service
from app.services.tts import get_tts_service
from app.services.tts.exceptions import ElevenLabsError
from app.services.tts.schemas import TTSRequest

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger(__name__)

CHUNK_SIZE = 32768
UPLOAD_DIR = Path(settings.audio_upload_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_FORMAT = "audio/mpeg"


def _role_allowed(role: str | None, allowed: set[str]) -> bool:
    if not role:
        return False
    return role == "admin" or role in allowed


def _session_questions(db: Session, session: models.InterviewSession) -> list[models.Question]:
    query = (
        db.query(models.Question)
        .filter(models.Question.job_role_id == session.job_role_id)
        .filter(models.Question.is_active.is_(True))
        .order_by(models.Question.id)
    )
    if session.template and session.template.question_count:
        query = query.limit(session.template.question_count)
    return query.all()


def _planned_questions(db: Session, session: models.InterviewSession) -> list[models.Question]:
    base_questions = _session_questions(db, session)
    plan = list((session.graph_state_json or {}).get("question_plan") or [])
    if not plan:
        plan = build_semantic_question_plan(db, session, base_questions)
    if not plan:
        return base_questions

    question_map = {question.id: question for question in base_questions}
    resolved: list[models.Question] = []
    for item in plan:
        existing = question_map.get(item["id"])
        if existing:
            resolved.append(existing)
            continue
        resolved.append(
            models.Question(
                id=item["id"],
                job_role_id=session.job_role_id,
                text=item["text"],
                category="dynamic",
                difficulty="adaptive",
                is_active=True,
            )
        )
    return resolved


def _resolve_session(db: Session, session_id: str) -> models.InterviewSession | None:
    return (
        db.query(models.InterviewSession)
        .options(
            selectinload(models.InterviewSession.candidate),
            selectinload(models.InterviewSession.job_role),
            selectinload(models.InterviewSession.template),
            selectinload(models.InterviewSession.answers),
        )
        .filter(models.InterviewSession.id == session_id)
        .first()
    )


def _current_question(session: models.InterviewSession) -> schemas.SessionQuestion | None:
    if not session.current_question_text:
        return None
    return schemas.SessionQuestion(
        id=session.current_question_id or "",
        text=session.current_question_text,
        category="dynamic",
        difficulty="adaptive",
    )


def _state_event(db: Session, session: models.InterviewSession, event_type: str = "session_state", message: str | None = None) -> schemas.InterviewSocketEvent:
    questions = _planned_questions(db, session)
    answered_questions = len(session.answers)
    return schemas.InterviewSocketEvent(
        type=event_type,
        interview_language=get_interview_language(session),
        status=session.status,
        message=message,
        current_question=_current_question(session),
        answered_questions=answered_questions,
        total_questions=len(questions),
        is_complete=session.status == "completed" or not session.current_question_text,
    )


async def _send_event(websocket: WebSocket, event: schemas.InterviewSocketEvent) -> None:
    await websocket.send_text(event.model_dump_json())


async def _stream_tts(websocket: WebSocket, session: models.InterviewSession, text: str) -> None:
    if not text:
        return
    tts_service = get_tts_service()
    await _send_event(
        websocket,
        schemas.InterviewSocketEvent(
            type="tts_started",
            interview_language=get_interview_language(session),
            status=session.status,
            message=text,
            question_id=session.current_question_id,
            audio_format=AUDIO_FORMAT,
        ),
    )

    request = TTSRequest(text=text, session_id=session.id, language=get_interview_language(session))
    try:
        async for chunk in tts_service.synthesize(request):
            await websocket.send_bytes(chunk)
    except ElevenLabsError as exc:
        logger.warning("TTS unavailable for session %s: %s", session.id, exc)
        await _send_event(
            websocket,
            schemas.InterviewSocketEvent(
                type="error",
                interview_language=get_interview_language(session),
                status=session.status,
                message="TTS unavailable. Falling back to browser audio.",
                question_id=session.current_question_id,
            ),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected TTS failure for session %s", session.id)
        await _send_event(
            websocket,
            schemas.InterviewSocketEvent(
                type="error",
                interview_language=get_interview_language(session),
                status=session.status,
                message=f"TTS unavailable. Falling back to browser audio. ({exc})",
                question_id=session.current_question_id,
            ),
        )
    finally:
        await _send_event(
            websocket,
            schemas.InterviewSocketEvent(
                type="tts_finished",
                interview_language=get_interview_language(session),
                status=session.status,
                question_id=session.current_question_id,
                audio_format=AUDIO_FORMAT,
            ),
        )


@router.websocket("/interviews/{session_id}")
async def interview_audio_socket(websocket: WebSocket, session_id: str):
    role = get_websocket_role(websocket)
    db = SessionLocal()
    audio_buffer = bytearray()
    active_question_id: str | None = None
    active_content_type = "audio/webm"
    active_language = "en"

    try:
        session = _resolve_session(db, session_id)
        candidate_token = websocket.query_params.get("token")
        is_candidate = bool(candidate_token and session and session.candidate.access_token == candidate_token)
        if not _role_allowed(role, {"interviewer"}) and not is_candidate:
            await websocket.close(code=1008)
            return

        await websocket.accept()
        if not session:
            await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Interview not found"))
            await websocket.close(code=1008)
            return

        while True:
            message = await websocket.receive()

            if "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Invalid JSON payload"))
                    continue

                msg_type = payload.get("type")

                if msg_type in {"session.sync", "question.request"}:
                    requested_language = payload.get("language")
                    if requested_language:
                        set_interview_language(session, requested_language)
                        db.commit()
                        db.refresh(session)
                    questions = _session_questions(db, session)
                    if session.status != "completed" and not (session.graph_state_json or {}).get("last_question"):
                        initialize_interview_graph(db, session, questions, language=get_interview_language(session))
                        db.commit()
                        db.refresh(session)
                        session = _resolve_session(db, session_id)
                    await _send_event(websocket, _state_event(db, session, event_type="question", message=session.current_question_text))
                    if payload.get("speak", True) and session.current_question_text:
                        await _stream_tts(websocket, session, session.current_question_text)
                    continue

                if msg_type == "clarify":
                    clarification = clarify_current_question(session)
                    db.commit()
                    db.refresh(session)
                    session = _resolve_session(db, session_id)
                    await _send_event(
                        websocket,
                        schemas.InterviewSocketEvent(
                            type="clarification",
                            interview_language=get_interview_language(session),
                            status=session.status,
                            message=clarification.message,
                            current_question=_current_question(session),
                            answered_questions=len(session.answers),
                            total_questions=len(_planned_questions(db, session)),
                        ),
                    )
                    if payload.get("speak", True) and clarification.message:
                        await _stream_tts(websocket, session, clarification.message)
                    continue

                if msg_type == "skip":
                    if not session.current_question_id:
                        await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="No current question to skip"))
                        continue
                    existing = (
                        db.query(models.Answer)
                        .filter(
                            models.Answer.session_id == session.id,
                            models.Answer.question_id == session.current_question_id,
                        )
                        .first()
                    )
                    if existing:
                        await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Answer already submitted for this question"))
                        continue
                    question_number = len(session.answers) + 1
                    answer = models.Answer(
                        session_id=session.id,
                        question_id=session.current_question_id,
                        question_number=question_number,
                        transcript="[SKIPPED]",
                    )
                    db.add(answer)
                    db.flush()
                    turn_result = skip_current_question(session, question_number=question_number)
                    db.commit()
                    db.refresh(session)
                    session = _resolve_session(db, session_id)
                    await _send_event(
                        websocket,
                        schemas.InterviewSocketEvent(
                            type="answer_saved",
                            interview_language=get_interview_language(session),
                            status=session.status,
                            message="Question skipped.",
                            question_id=answer.question_id,
                            candidate_answer_saved=True,
                            answered_questions=len(session.answers),
                            total_questions=len(_planned_questions(db, session)),
                        ),
                    )
                    await _send_event(
                        websocket,
                        schemas.InterviewSocketEvent(
                            type="evaluation_ready",
                            interview_language=get_interview_language(session),
                            status=session.status,
                            evaluation=turn_result.last_evaluation,
                        ),
                    )
                    next_type = "session_completed" if turn_result.is_complete else "question"
                    await _send_event(websocket, _state_event(db, session, event_type=next_type, message=session.current_question_text or "Interview completed."))
                    if not turn_result.is_complete and payload.get("speak", True) and session.current_question_text:
                        await _stream_tts(websocket, session, session.current_question_text)
                    continue

                if msg_type == "answer.start":
                    if not session.current_question_id:
                        await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="No active question available"))
                        continue
                    active_question_id = payload.get("question_id") or session.current_question_id
                    if active_question_id != session.current_question_id:
                        await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Question does not match current state"))
                        continue
                    active_content_type = payload.get("content_type") or "audio/webm"
                    active_language = payload.get("language") or get_interview_language(session)
                    audio_buffer = bytearray()
                    await _send_event(
                        websocket,
                        schemas.InterviewSocketEvent(
                            type="recording_ready",
                            interview_language=get_interview_language(session),
                            status=session.status,
                            question_id=active_question_id,
                        ),
                    )
                    continue

                if msg_type == "answer.end":
                    if not active_question_id:
                        await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="No active recording"))
                        continue
                    if not session.current_question_id or active_question_id != session.current_question_id:
                        await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Current question changed before answer was processed"))
                        active_question_id = None
                        audio_buffer = bytearray()
                        continue
                    existing = (
                        db.query(models.Answer)
                        .filter(
                            models.Answer.session_id == session.id,
                            models.Answer.question_id == active_question_id,
                        )
                        .first()
                    )
                    if existing:
                        await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Answer already submitted for this question"))
                        active_question_id = None
                        audio_buffer = bytearray()
                        continue

                    transcript = (payload.get("transcript") or "").strip()
                    stt_duration = payload.get("audio_duration_sec")
                    if not transcript and audio_buffer:
                        try:
                            stt_result = await get_stt_service().transcribe(
                                bytes(audio_buffer),
                                filename=f"{session.id}_{active_question_id}.webm",
                                content_type=active_content_type,
                                language=active_language,
                            )
                            transcript = stt_result.get("text", "").strip()
                            stt_duration = stt_result.get("duration")
                            active_language = stt_result.get("language", active_language)
                        except Exception as exc:
                            await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message=f"Transcription failed: {exc}"))
                            active_question_id = None
                            audio_buffer = bytearray()
                            continue

                    if not transcript:
                        await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Empty transcript. Please try again."))
                        active_question_id = None
                        audio_buffer = bytearray()
                        continue

                    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                    audio_path = None
                    if audio_buffer:
                        audio_path = UPLOAD_DIR / f"{session.id}_{active_question_id}_{timestamp}.bin"
                        audio_path.write_bytes(bytes(audio_buffer))

                    question_number = len(session.answers) + 1
                    answer = models.Answer(
                        session_id=session.id,
                        question_id=active_question_id,
                        question_number=question_number,
                        transcript=transcript,
                        audio_url=str(audio_path) if audio_path else None,
                        audio_duration_sec=stt_duration,
                    )
                    db.add(answer)
                    db.flush()
                    turn_result = submit_interview_answer(session, transcript)
                    db.commit()
                    db.refresh(session)
                    session = _resolve_session(db, session_id)

                    await _send_event(
                        websocket,
                        schemas.InterviewSocketEvent(
                            type="transcript_final",
                            interview_language=get_interview_language(session),
                            status=session.status,
                            transcript=transcript,
                            question_id=active_question_id,
                        ),
                    )
                    await _send_event(
                        websocket,
                        schemas.InterviewSocketEvent(
                            type="answer_saved",
                            interview_language=get_interview_language(session),
                            status=session.status,
                            question_id=active_question_id,
                            candidate_answer_saved=True,
                            answered_questions=len(session.answers),
                            total_questions=len(_planned_questions(db, session)),
                        ),
                    )
                    await _send_event(
                        websocket,
                        schemas.InterviewSocketEvent(
                            type="evaluation_ready",
                            interview_language=get_interview_language(session),
                            status=session.status,
                            evaluation=turn_result.last_evaluation,
                        ),
                    )
                    next_type = "session_completed" if turn_result.is_complete else "question"
                    await _send_event(websocket, _state_event(db, session, event_type=next_type, message=session.current_question_text or "Interview completed."))
                    if not turn_result.is_complete and payload.get("speak", True) and session.current_question_text:
                        await _stream_tts(websocket, session, session.current_question_text)
                    active_question_id = None
                    audio_buffer = bytearray()
                    continue

                await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Unknown message type"))
                continue

            if "bytes" in message and message["bytes"] is not None:
                if not active_question_id:
                    await _send_event(websocket, schemas.InterviewSocketEvent(type="error", message="Send answer.start first"))
                    continue
                audio_buffer.extend(message["bytes"])
                continue

    finally:
        db.close()
