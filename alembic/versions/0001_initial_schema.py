"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-04-07 11:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment]

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    op.create_table(
        "job_roles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("seniority", sa.String(length=20), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("skills_required", postgresql.ARRAY(sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "candidates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("cv_summary", sa.Text(), nullable=True),
        sa.Column("skills", postgresql.ARRAY(sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON(), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("access_token", sa.String(length=64), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_candidates_access_token", "candidates", ["access_token"], unique=True)

    op.create_table(
        "questions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_role_id", sa.String(length=36), sa.ForeignKey("job_roles.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("difficulty", sa.String(length=10), nullable=False),
        sa.Column(
            "embedding",
            Vector(1536) if Vector is not None and bind.dialect.name == "postgresql" else sa.JSON(),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_questions_job_role_id", "questions", ["job_role_id"], unique=False)

    op.create_table(
        "interview_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_role_id", sa.String(length=36), sa.ForeignKey("job_roles.id"), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("max_time_per_question_sec", sa.Integer(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("evaluation_criteria", sa.Text(), nullable=True),
    )
    op.create_index("ix_interview_templates_job_role_id", "interview_templates", ["job_role_id"], unique=False)

    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("job_role_id", sa.String(length=36), sa.ForeignKey("job_roles.id"), nullable=False),
        sa.Column("template_id", sa.String(length=36), sa.ForeignKey("interview_templates.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("current_question_id", sa.String(length=36), nullable=True),
        sa.Column("current_question_text", sa.Text(), nullable=True),
        sa.Column("current_question_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clarification_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skip_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_intent", sa.String(length=30), nullable=True),
        sa.Column("graph_state_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_interview_sessions_candidate_id", "interview_sessions", ["candidate_id"], unique=False)
    op.create_index("ix_interview_sessions_job_role_id", "interview_sessions", ["job_role_id"], unique=False)
    op.create_index("ix_interview_sessions_template_id", "interview_sessions", ["template_id"], unique=False)

    op.create_table(
        "answers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("interview_sessions.id"), nullable=False),
        sa.Column("question_id", sa.String(length=36), sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("question_number", sa.Integer(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column("audio_duration_sec", sa.Numeric(6, 2), nullable=True),
        sa.Column("stt_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_answers_session_id", "answers", ["session_id"], unique=False)
    op.create_index("ix_answers_question_id", "answers", ["question_id"], unique=False)

    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("interview_sessions.id"), nullable=False),
        sa.Column("score", sa.Numeric(4, 1), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("areas_of_improvement", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.String(length=20), nullable=False),
        sa.Column("model_used", sa.String(length=50), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_evaluations_session_id", "evaluations", ["session_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_evaluations_session_id", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index("ix_answers_question_id", table_name="answers")
    op.drop_index("ix_answers_session_id", table_name="answers")
    op.drop_table("answers")
    op.drop_index("ix_interview_sessions_template_id", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_job_role_id", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_candidate_id", table_name="interview_sessions")
    op.drop_table("interview_sessions")
    op.drop_index("ix_interview_templates_job_role_id", table_name="interview_templates")
    op.drop_table("interview_templates")
    op.drop_index("ix_questions_job_role_id", table_name="questions")
    op.drop_table("questions")
    op.drop_index("ix_candidates_access_token", table_name="candidates")
    op.drop_table("candidates")
    op.drop_table("job_roles")
    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")
