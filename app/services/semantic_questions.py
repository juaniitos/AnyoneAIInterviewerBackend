from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from sqlalchemy.orm import Session

from app import models
from app.core.config import settings

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_+-]+")


def _tokenize(text: str) -> list[str]:
    normalized = text.lower()
    normalized = (
        normalized.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    return TOKEN_PATTERN.findall(normalized)


def _hashed_index(token: str, dimensions: int) -> int:
    return abs(hash(token)) % dimensions


def _l2_normalize(values: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0:
        return values
    return [value / magnitude for value in values]


def _as_list(values: Iterable[float] | None) -> list[float]:
    if values is None:
        return []
    return list(values)


def build_embedding(text: str, *, dimensions: int | None = None) -> list[float]:
    dims = dimensions or settings.embedding_dimension
    vector = [0.0] * dims
    token_counts = Counter(_tokenize(text))
    for token, count in token_counts.items():
        vector[_hashed_index(token, dims)] += 1.0 + math.log1p(count)
    return _l2_normalize(vector)


def cosine_similarity(left: Iterable[float] | None, right: Iterable[float] | None) -> float:
    left_list = _as_list(left)
    right_list = _as_list(right)
    if not left_list or not right_list:
        return 0.0
    return sum(a * b for a, b in zip(left_list, right_list))


def build_question_corpus(question: models.Question, role: models.JobRole | None = None) -> str:
    skills = ", ".join(role.skills_required or []) if role else ""
    role_name = role.name if role else ""
    department = role.department if role else ""
    return " | ".join(
        part
        for part in [
            question.text,
            question.category,
            question.difficulty,
            role_name,
            department,
            skills,
        ]
        if part
    )


def build_interview_query(
    *,
    role: models.JobRole,
    candidate: models.Candidate | None,
    template: models.InterviewTemplate | None,
) -> str:
    candidate_skills = ", ".join(candidate.skills or []) if candidate and candidate.skills else ""
    template_hints = template.evaluation_criteria if template else ""
    role_skills = ", ".join(role.skills_required or [])
    return " | ".join(
        part
        for part in [
            role.name,
            role.description or "",
            role.department or "",
            role.seniority or "",
            role_skills,
            candidate_skills,
            template_hints or "",
        ]
        if part
    )


def ensure_question_embedding(question: models.Question, role: models.JobRole | None = None) -> bool:
    if len(_as_list(question.embedding)) > 0:
        return False
    question.embedding = build_embedding(build_question_corpus(question, role))
    return True


def ensure_role_question_embeddings(db: Session, role: models.JobRole) -> None:
    changed = False
    questions = (
        db.query(models.Question)
        .filter(models.Question.job_role_id == role.id)
        .filter(models.Question.is_active.is_(True))
        .all()
    )
    for question in questions:
        changed = ensure_question_embedding(question, role) or changed
    if changed:
        db.flush()


def select_semantic_questions(
    db: Session,
    *,
    role: models.JobRole,
    candidate: models.Candidate | None,
    template: models.InterviewTemplate | None,
    limit: int,
) -> list[models.Question]:
    questions = (
        db.query(models.Question)
        .filter(models.Question.job_role_id == role.id)
        .filter(models.Question.is_active.is_(True))
        .all()
    )
    if not questions:
        return []

    ensure_role_question_embeddings(db, role)
    query_embedding = build_embedding(
        build_interview_query(role=role, candidate=candidate, template=template)
    )

    ranked = []
    for question in questions:
        score = cosine_similarity(question.embedding, query_embedding)
        ranked.append((score, question))

    ranked.sort(key=lambda item: (item[0], item[1].difficulty, item[1].text), reverse=True)

    selected: list[models.Question] = []
    used_categories: set[str] = set()
    for _, question in ranked:
        if len(selected) >= limit:
            break
        if question.category not in used_categories:
            selected.append(question)
            used_categories.add(question.category)

    if len(selected) < min(limit, len(questions)):
        selected_ids = {question.id for question in selected}
        for _, question in ranked:
            if len(selected) >= limit:
                break
            if question.id in selected_ids:
                continue
            selected.append(question)

    return selected[:limit]
