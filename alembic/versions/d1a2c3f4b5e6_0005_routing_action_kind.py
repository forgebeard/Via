"""0005_routing_action_kind

Revision ID: d1a2c3f4b5e6
Revises: c4b7f6e2a901
Create Date: 2026-05-06 15:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1a2c3f4b5e6"
down_revision: Union[str, None] = "c4b7f6e2a901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "routing_policies",
        sa.Column("action_kind", sa.String(length=16), nullable=True),
    )
    op.create_index(
        op.f("ix_routing_policies_action_kind"),
        "routing_policies",
        ["action_kind"],
        unique=False,
    )
    op.execute(
        """
        UPDATE routing_policies rp
        SET action_kind = CASE nt.key
            WHEN 'new' THEN 'created'
            WHEN 'reopened' THEN 'updated'
            WHEN 'info' THEN 'updated'
            WHEN 'issue_updated' THEN 'updated'
            WHEN 'status_change' THEN 'updated'
            ELSE NULL
        END
        FROM notification_types nt
        WHERE rp.notification_type_id = nt.id
        """
    )
    op.execute("DELETE FROM routing_policies WHERE action_kind IS NULL")
    op.alter_column("routing_policies", "action_kind", nullable=False)
    op.alter_column("routing_policies", "notification_type_id", nullable=True)
    op.execute("UPDATE routing_policies SET notification_type_id = NULL, target_kind = 'both'")


def downgrade() -> None:
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
    op.drop_index(op.f("ix_routing_policies_action_kind"), table_name="routing_policies")
    op.drop_column("routing_policies", "action_kind")
