"""0007_routing_policies_enabled_true

Revision ID: f1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-05-08 00:00:00.000000

Продуктовый инвариант: правило либо удалено, либо существует и включено.
Историческое значение enabled=false выравниваем к true. Колонку оставляем
как есть, чтобы не ломать совместимость с моделью и кодом, читающим её.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE routing_policies SET enabled = true WHERE enabled = false"
    )


def downgrade() -> None:
    # Прежние значения enabled=false восстановить без бэкапа невозможно:
    # инвариант продукта изменился, исторические выключенные правила были
    # либо удалены пользователем, либо нормализованы upgrade-ом.
    pass
