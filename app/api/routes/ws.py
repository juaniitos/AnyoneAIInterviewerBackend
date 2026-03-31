import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, WebSocket
from sqlalchemy.orm import Session
from app import models
from app.db.session import SessionLocal
from app.core.config import settings
from app.security.auth import get_websocket_role

router = APIRouter(prefix="/ws", tags=["websocket"])

CHUNK_SIZE = 32768
UPLOAD_DIR = Path(settings.audio_upload_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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


@router.websocket("/interviews/{session_id}")
async def interview_audio_socket(websocket: WebSocket, session_id: str):
    role = get_websocket_role(websocket)
    if not _role_allowed(role, {"interviewer"}):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    db = SessionLocal()

    try:
        session = (
            db.query(models.InterviewSession)
            .filter(models.InterviewSession.id == session_id)
            .first()
        )
        if not session:
            await websocket.send_text(json.dumps({"type": "error", "detail": "Interview not found"}))
            await websocket.close(code=1008)
            return

        current_file = None
        current_path = None
        current_question_id = None
        current_content_type = None

        while True:
            message = await websocket.receive()

            if "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({"type": "error", "detail": "Invalid JSON"}))
                    continue

                msg_type = payload.get("type")
                if msg_type == "start":
                    question_id = payload.get("question_id")
                    if not question_id:
                        await websocket.send_text(
                            json.dumps({"type": "error", "detail": "question_id is required"})
                        )
                        continue

                    question = (
                        db.query(models.Question)
                        .filter(
                            models.Question.id == question_id,
                            models.Question.job_role_id == session.job_role_id,
                        )
                        .first()
                    )
                    if not question:
                        await websocket.send_text(json.dumps({"type": "error", "detail": "Question not found"}))
                        continue

                    if current_file:
                        current_file.close()

                    current_question_id = question_id
                    current_content_type = payload.get("content_type") or "application/octet-stream"
                    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                    current_path = UPLOAD_DIR / f"{session_id}_{question_id}_{timestamp}.bin"
                    current_file = current_path.open("wb")

                    await websocket.send_text(
                        json.dumps({"type": "ready", "question_id": question_id})
                    )
                    continue

                if msg_type == "end":
                    if not current_file or not current_question_id:
                        await websocket.send_text(
                            json.dumps({"type": "error", "detail": "No active recording"})
                        )
                        continue

                    current_file.close()

                    questions = _session_questions(db, session)
                    question_map = {q.id: idx + 1 for idx, q in enumerate(questions)}
                    question_number = payload.get("question_number") or question_map.get(current_question_id) or 1

                    existing = (
                        db.query(models.Answer)
                        .filter(
                            models.Answer.session_id == session_id,
                            models.Answer.question_id == current_question_id,
                        )
                        .first()
                    )
                    if existing:
                        await websocket.send_text(
                            json.dumps({"type": "error", "detail": "Answer already submitted"})
                        )
                        current_file = None
                        current_question_id = None
                        current_path = None
                        continue

                    answer = models.Answer(
                        session_id=session_id,
                        question_id=current_question_id,
                        question_number=question_number,
                        transcript=payload.get("transcript", ""),
                        audio_url=str(current_path) if current_path else None,
                        audio_duration_sec=payload.get("audio_duration_sec"),
                        stt_confidence=payload.get("stt_confidence"),
                    )
                    db.add(answer)
                    db.commit()
                    db.refresh(answer)

                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "saved",
                                "answer_id": answer.id,
                                "audio_url": answer.audio_url,
                                "content_type": current_content_type,
                            }
                        )
                    )

                    current_file = None
                    current_question_id = None
                    current_path = None
                    continue

                if msg_type == "playback":
                    question_id = payload.get("question_id")
                    if not question_id:
                        await websocket.send_text(
                            json.dumps({"type": "error", "detail": "question_id is required"})
                        )
                        continue

                    answer = (
                        db.query(models.Answer)
                        .filter(
                            models.Answer.session_id == session_id,
                            models.Answer.question_id == question_id,
                        )
                        .order_by(models.Answer.created_at.desc())
                        .first()
                    )
                    if not answer or not answer.audio_url:
                        await websocket.send_text(
                            json.dumps({"type": "error", "detail": "No audio available"})
                        )
                        continue

                    audio_path = Path(answer.audio_url)
                    if not audio_path.exists():
                        await websocket.send_text(
                            json.dumps({"type": "error", "detail": "Audio file missing"})
                        )
                        continue

                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "audio_start",
                                "question_id": question_id,
                            }
                        )
                    )
                    with audio_path.open("rb") as audio_file:
                        while True:
                            chunk = audio_file.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            await websocket.send_bytes(chunk)
                    await websocket.send_text(json.dumps({"type": "audio_end"}))
                    continue

                await websocket.send_text(json.dumps({"type": "error", "detail": "Unknown message type"}))
                continue

            if "bytes" in message and message["bytes"] is not None:
                if not current_file:
                    await websocket.send_text(
                        json.dumps({"type": "error", "detail": "Send start first"})
                    )
                    continue
                current_file.write(message["bytes"])
                current_file.flush()
                continue

    finally:
        if "current_file" in locals() and current_file:
            current_file.close()
        db.close()
