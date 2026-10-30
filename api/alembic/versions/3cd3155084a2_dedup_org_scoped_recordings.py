"""dedup recordings to org-scoped unique audio

Revision ID: 3cd3155084a2
Revises: e7254d2c6c18
Create Date: 2026-04-10 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3cd3155084a2"
down_revision: Union[str, None] = "e7254d2c6c18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep this data migration runnable both online and through Alembic's
    # offline SQL renderer. An explicit PostgreSQL block preserves the
    # row-by-row remapping behavior without fetching results from the
    # migration connection (which has no result set in offline mode).
    op.execute(sa.text("""
        DO $$
        DECLARE
            duplicate RECORD;
            alias_pattern TEXT;
            canonical_pattern TEXT;
        BEGIN
            FOR duplicate IN
            WITH ranked AS (
                SELECT
                    recording_id,
                    organization_id,
                    transcript,
                    tts_provider,
                    tts_model,
                    tts_voice_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY organization_id, transcript,
                                     tts_provider, tts_model, tts_voice_id
                        ORDER BY created_at ASC
                    ) AS rn
                FROM workflow_recordings
                WHERE is_active = true
            ),
            canonical AS (
                SELECT recording_id AS canonical_id,
                       organization_id, transcript,
                       tts_provider, tts_model, tts_voice_id
                FROM ranked
                WHERE rn = 1
            )
            SELECT r.recording_id AS alias_id, c.canonical_id
            FROM ranked r
            JOIN canonical c
              ON  r.organization_id = c.organization_id
              AND r.transcript      = c.transcript
              AND r.tts_provider    = c.tts_provider
              AND r.tts_model       = c.tts_model
              AND r.tts_voice_id    = c.tts_voice_id
            WHERE r.rn > 1
            LOOP
                alias_pattern := 'RECORDING_ID: ' || duplicate.alias_id;
                canonical_pattern := 'RECORDING_ID: ' || duplicate.canonical_id;

                -- Remap IDs in both draft and published workflow JSON.
                UPDATE workflows
                SET workflow_definition =
                    REPLACE(workflow_definition::text, alias_pattern, canonical_pattern)::json
                WHERE workflow_definition::text LIKE '%' || alias_pattern || '%';

                UPDATE workflow_definitions
                SET workflow_json =
                    REPLACE(workflow_json::text, alias_pattern, canonical_pattern)::json
                WHERE workflow_json::text LIKE '%' || alias_pattern || '%';

                -- Soft-delete every alias only after its references are remapped.
                UPDATE workflow_recordings
                SET is_active = false
                WHERE recording_id = duplicate.alias_id
                  AND is_active = true;
            END LOOP;
        END $$
    """))


def downgrade() -> None:
    # Deduplication is a one-way data migration.  The soft-deleted rows
    # still exist in the table; a manual restore is possible if needed.
    pass
