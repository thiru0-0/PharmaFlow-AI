"""initial schema + db-level state-machine guards

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-10

The ORM metadata is the single source of truth for table structure, so this migration
materialises it via create_all and then installs the dialect-specific triggers that
enforce the batch lifecycle and the certificate gate at the database layer.
"""
from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.db.guards import install_guards
import app.models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    install_guards(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
