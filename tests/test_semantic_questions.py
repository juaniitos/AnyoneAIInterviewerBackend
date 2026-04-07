from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.db.base import Base
from app.services.semantic_questions import build_embedding, cosine_similarity, select_semantic_questions


def test_build_embedding_is_deterministic():
    left = build_embedding("FastAPI observability retries")
    right = build_embedding("FastAPI observability retries")

    assert left == right
    assert len(left) == 1536


def test_select_semantic_questions_prefers_matching_skills(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'semantic_questions.db'}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    try:
        db = SessionLocal()
        role = models.JobRole(
            name="Platform Engineer",
            description="Own observability, APIs, and backend reliability.",
            seniority="senior",
            department="Engineering",
            skills_required=["FastAPI", "Observability", "Python"],
        )
        db.add(role)
        db.flush()

        template = models.InterviewTemplate(
            job_role_id=role.id,
            name="Platform Core",
            question_count=2,
            max_time_per_question_sec=120,
            system_prompt="Interview the candidate.",
            evaluation_criteria="Reliability and tradeoffs.",
        )
        candidate = models.Candidate(
            full_name="Jordan",
            email="jordan@example.com",
            skills=["FastAPI", "Monitoring"],
            access_token="token",
            token_expires_at=datetime(2030, 1, 1),
        )
        db.add(template)
        db.add(candidate)
        db.flush()

        db.add_all(
            [
                models.Question(
                    job_role_id=role.id,
                    text="How would you monitor failures in production APIs?",
                    category="operations",
                    difficulty="medium",
                    is_active=True,
                ),
                models.Question(
                    job_role_id=role.id,
                    text="How do you design a resilient FastAPI service?",
                    category="system_design",
                    difficulty="hard",
                    is_active=True,
                ),
                models.Question(
                    job_role_id=role.id,
                    text="Tell me about a conflict with a stakeholder.",
                    category="behavioral",
                    difficulty="medium",
                    is_active=True,
                ),
            ]
        )
        db.commit()

        selected = select_semantic_questions(
            db,
            role=role,
            candidate=candidate,
            template=template,
            limit=2,
        )

        selected_texts = [question.text for question in selected]
        assert len(selected_texts) == 2
        assert any("FastAPI" in text or "monitor" in text.lower() for text in selected_texts)
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_cosine_similarity_rewards_related_text():
    api = build_embedding("FastAPI reliability monitoring tracing")
    related = build_embedding("API tracing and monitoring for reliability")
    unrelated = build_embedding("Candidate empathy negotiation stakeholder conflict")

    assert cosine_similarity(api, related) > cosine_similarity(api, unrelated)
