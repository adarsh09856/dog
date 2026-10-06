"""add status to organizations table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-06 17:25:00.000000

"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()

    if "organizations" in tables:
        org_cols = [c["name"] for c in inspector.get_columns("organizations")]
        if "status" not in org_cols:
            op.add_column(
                "organizations",
                sa.Column("status", sa.String(), nullable=False, server_default="active"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()

    if "organizations" in tables:
        org_cols = [c["name"] for c in inspector.get_columns("organizations")]
        if "status" in org_cols:
            op.drop_column("organizations", "status")
