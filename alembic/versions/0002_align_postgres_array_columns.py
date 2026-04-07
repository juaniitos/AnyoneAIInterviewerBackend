"""align postgres array columns

Revision ID: 0002_align_pg_arrays
Revises: 0001_initial_schema
Create Date: 2026-04-07 17:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_align_pg_arrays"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_column("job_roles", "skills_required")
    op.add_column("job_roles", sa.Column("skills_required", postgresql.ARRAY(sa.Text()), nullable=True))

    op.drop_column("candidates", "skills")
    op.add_column("candidates", sa.Column("skills", postgresql.ARRAY(sa.Text()), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_column("candidates", "skills")
    op.add_column("candidates", sa.Column("skills", sa.JSON(), nullable=True))

    op.drop_column("job_roles", "skills_required")
    op.add_column("job_roles", sa.Column("skills_required", sa.JSON(), nullable=True))
