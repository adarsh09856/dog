"""add is_active to users

Revision ID: f4b18c7d9a01
Revises: f1a89c3d4b2e
Create Date: 2026-10-03 12:00:00.000000

"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "f4b18c7d9a01"
down_revision: Union[str, None] = "f1a89c3d4b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = [c["name"] for c in inspector.get_columns("users")]
    if "is_active" not in columns:
        op.add_column(
            "users",
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = [c["name"] for c in inspector.get_columns("users")]
    if "is_active" in columns:
        op.drop_column("users", "is_active")
