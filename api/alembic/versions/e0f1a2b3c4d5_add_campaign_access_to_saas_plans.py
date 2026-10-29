"""Add campaign access as an explicit SaaS plan entitlement."""

import sqlalchemy as sa
from alembic import op


revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "saas_plans",
        sa.Column("has_campaigns_access", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("saas_plans", "has_campaigns_access", server_default=None)


def downgrade() -> None:
    op.drop_column("saas_plans", "has_campaigns_access")
