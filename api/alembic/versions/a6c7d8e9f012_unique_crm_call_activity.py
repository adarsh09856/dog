"""make CRM call activities idempotent by workflow run

Revision ID: a6c7d8e9f012
Revises: 0a6b9f2e3c41
Create Date: 2026-11-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a6c7d8e9f012"
down_revision: str = "0a6b9f2e3c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_lead_activities_call_id", "lead_activities", ["call_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_lead_activities_call_id", "lead_activities", type_="unique"
    )
