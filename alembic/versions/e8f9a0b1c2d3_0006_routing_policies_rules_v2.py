"""0006_routing_policies_rules_v2

Revision ID: e8f9a0b1c2d3
Revises: d1a2c3f4b5e6
Create Date: 2026-05-07 00:00:00.000000

Rules v2: recipient_modes JSONB; drop routing_policies.priority/sort_order;
backfill notification_type_id from action_kind.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d1a2c3f4b5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "routing_policies",
        sa.Column(
            "recipient_modes",
            JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[\"match_rooms\"]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE routing_policies rp
        SET notification_type_id = nt.id
        FROM notification_types nt
        WHERE rp.notification_type_id IS NULL
          AND nt.key = CASE rp.action_kind
            WHEN 'created' THEN 'new'
            ELSE 'issue_updated'
          END
        """
    )
    op.execute("DELETE FROM routing_policies WHERE notification_type_id IS NULL")
    op.alter_column("routing_policies", "notification_type_id", nullable=False)
    op.drop_column("routing_policies", "priority")
    op.drop_column("routing_policies", "sort_order")


def downgrade() -> None:
    op.add_column(
        "routing_policies",
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "routing_policies",
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
    )
    op.alter_column("routing_policies", "notification_type_id", nullable=True)
    op.drop_column("routing_policies", "recipient_modes")
