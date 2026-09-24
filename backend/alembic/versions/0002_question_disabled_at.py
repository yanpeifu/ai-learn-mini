"""question.disabled_at: 被举报下线的题目不再下发（M3-06）

Revision ID: 0002_question_disabled
Revises: ba9c0649ba60
Create Date: 2026-09-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.db.types

revision: str = "0002_question_disabled"
down_revision: Union[str, None] = "ba9c0649ba60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "disabled_at",
                app.db.types.UTCDateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.drop_column("disabled_at")
