"""0011_drop_legacy_routing

Удаление legacy-маршрутизации: таблицы маршрутов/дайджестов/M2M target,
столбец routing_policies.target_kind; зачистка осиротевших notification_types.

Revision ID: c3e9f1a4b7d2
Revises: b2c3d4e5f6a7
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3e9f1a4b7d2"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("notification_routing_rules")
    op.drop_table("routing_policy_target_users")
    op.drop_table("routing_policy_target_groups")
    op.drop_table("pending_digests")
    op.drop_table("user_version_routes")
    op.drop_table("group_version_routes")
    op.drop_table("status_room_routes")
    op.drop_table("version_room_routes")
    op.drop_column("routing_policies", "target_kind")
    op.execute(
        """
        DELETE FROM notification_types nt
        WHERE nt.key NOT IN ('new', 'reminder', 'issue_updated', 'daily_report')
          AND NOT EXISTS (
              SELECT 1 FROM routing_policies rp WHERE rp.notification_type_id = nt.id
          )
        """
    )


def downgrade() -> None:
    raise NotImplementedError("0011_drop_legacy_routing: downgrade не поддерживается")
