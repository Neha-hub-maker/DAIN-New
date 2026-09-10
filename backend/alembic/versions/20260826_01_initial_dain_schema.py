"""Initial DAIN schema.

Revision ID: 20260826_01
Revises:
Create Date: 2026-08-26
"""

from alembic import op

from app.db.base import Base
import app.models.dain  # noqa: F401 -- loads model metadata


revision = "20260826_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
