"""Store owner-observed source IP for installation checks."""

import sqlalchemy as sa
from alembic import op

revision = "e31f4a920b6c"
down_revision = "c29e8a75d41b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("client_installations", sa.Column("observed_ip", sa.String(length=45), nullable=True))


def downgrade():
    op.drop_column("client_installations", "observed_ip")
