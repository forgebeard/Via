"""0015_journal_scope_seed

- Зарегистрировать умолчания журнального охвата в ``cycle_settings`` (idempotent).
- ``downgrade`` удаляет только строки, совпадающие с засеянными значениями, чтобы не трогать ручные правки.

Revision ID: a8f9e0d1c2b3
Revises: d4e5f6a7b8c0
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "a8f9e0d1c2b3"
down_revision: Union[str, None] = "d4e5f6a7b8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_SCOPE = "all"
_SEED_PROJECT_IDS = "[]"


def upgrade() -> None:
    op.execute(
        text(
            """
            INSERT INTO cycle_settings (key, value, description)
            SELECT 'JOURNAL_SCOPE_MODE', :scope, NULL
            WHERE NOT EXISTS (SELECT 1 FROM cycle_settings WHERE key = 'JOURNAL_SCOPE_MODE')
            """
        ).bindparams(scope=_SEED_SCOPE)
    )
    op.execute(
        text(
            """
            INSERT INTO cycle_settings (key, value, description)
            SELECT 'JOURNAL_PROJECT_IDS', :project_ids, NULL
            WHERE NOT EXISTS (SELECT 1 FROM cycle_settings WHERE key = 'JOURNAL_PROJECT_IDS')
            """
        ).bindparams(project_ids=_SEED_PROJECT_IDS)
    )


def downgrade() -> None:
    op.execute(
        text(
            """
            DELETE FROM cycle_settings
            WHERE key = 'JOURNAL_SCOPE_MODE' AND value = :scope
            """
        ).bindparams(scope=_SEED_SCOPE)
    )
    op.execute(
        text(
            """
            DELETE FROM cycle_settings
            WHERE key = 'JOURNAL_PROJECT_IDS' AND value = :project_ids
            """
        ).bindparams(project_ids=_SEED_PROJECT_IDS)
    )
