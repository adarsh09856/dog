"""Link website widgets to independently managed embed tokens."""

import sqlalchemy as sa
from alembic import op

revision = "e9c27a40b615"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "website_widgets", sa.Column("embed_token_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_website_widget_embed_token",
        "website_widgets",
        "embed_tokens",
        ["embed_token_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_website_widget_embed_token", "website_widgets", ["embed_token_id"]
    )


def downgrade():
    op.execute(
        "UPDATE embed_tokens SET is_active = false WHERE id IN (SELECT embed_token_id FROM website_widgets WHERE embed_token_id IS NOT NULL)"
    )
    op.drop_constraint(
        "uq_website_widget_embed_token", "website_widgets", type_="unique"
    )
    op.drop_constraint(
        "fk_website_widget_embed_token", "website_widgets", type_="foreignkey"
    )
    op.drop_column("website_widgets", "embed_token_id")
