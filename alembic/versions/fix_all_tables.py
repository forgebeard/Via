"""add redmine statuses, versions, priorities and bot columns

Revision ID: fix_all_tables
Revises: 0018_pending_notifications_dlq
Create Date: 2026-04-15 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fix_all_tables'
down_revision: Union[str, None] = '0018_pending_notifications_dlq'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    if not _has_table('redmine_statuses'):
        op.create_table(
            'redmine_statuses',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('redmine_status_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('is_closed', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('redmine_status_id'),
        )
    else:
        _add_column_if_missing(
            'redmine_statuses',
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        )
    _create_index_if_missing(op.f('ix_redmine_statuses_is_active'), 'redmine_statuses', ['is_active'])
    _create_index_if_missing(
        op.f('ix_redmine_statuses_redmine_status_id'),
        'redmine_statuses',
        ['redmine_status_id'],
        unique=True,
    )

    if not _has_table('redmine_versions'):
        op.create_table(
            'redmine_versions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('redmine_version_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('redmine_version_id'),
        )
    _create_index_if_missing(op.f('ix_redmine_versions_is_active'), 'redmine_versions', ['is_active'])
    _create_index_if_missing(
        op.f('ix_redmine_versions_redmine_version_id'),
        'redmine_versions',
        ['redmine_version_id'],
        unique=True,
    )

    if not _has_table('redmine_priorities'):
        op.create_table(
            'redmine_priorities',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('redmine_priority_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('redmine_priority_id'),
        )
    _create_index_if_missing(op.f('ix_redmine_priorities_is_active'), 'redmine_priorities', ['is_active'])
    _create_index_if_missing(
        op.f('ix_redmine_priorities_redmine_priority_id'),
        'redmine_priorities',
        ['redmine_priority_id'],
        unique=True,
    )

    _add_column_if_missing('bot_users', sa.Column('versions', sa.JSON(), nullable=False, server_default='["all"]'))
    _add_column_if_missing('bot_users', sa.Column('priorities', sa.JSON(), nullable=False, server_default='["all"]'))

    _add_column_if_missing('support_groups', sa.Column('versions', sa.JSON(), nullable=False, server_default='["all"]'))
    _add_column_if_missing('support_groups', sa.Column('priorities', sa.JSON(), nullable=False, server_default='["all"]'))


def downgrade() -> None:
    if _has_column('support_groups', 'priorities'):
        op.drop_column('support_groups', 'priorities')
    if _has_column('support_groups', 'versions'):
        op.drop_column('support_groups', 'versions')
    if _has_column('bot_users', 'priorities'):
        op.drop_column('bot_users', 'priorities')
    if _has_column('bot_users', 'versions'):
        op.drop_column('bot_users', 'versions')
    if _has_table('redmine_priorities'):
        if _has_index('redmine_priorities', op.f('ix_redmine_priorities_redmine_priority_id')):
            op.drop_index(op.f('ix_redmine_priorities_redmine_priority_id'), table_name='redmine_priorities')
        if _has_index('redmine_priorities', op.f('ix_redmine_priorities_is_active')):
            op.drop_index(op.f('ix_redmine_priorities_is_active'), table_name='redmine_priorities')
        op.drop_table('redmine_priorities')
    if _has_table('redmine_versions'):
        if _has_index('redmine_versions', op.f('ix_redmine_versions_redmine_version_id')):
            op.drop_index(op.f('ix_redmine_versions_redmine_version_id'), table_name='redmine_versions')
        if _has_index('redmine_versions', op.f('ix_redmine_versions_is_active')):
            op.drop_index(op.f('ix_redmine_versions_is_active'), table_name='redmine_versions')
        op.drop_table('redmine_versions')
    if _has_index('redmine_statuses', op.f('ix_redmine_statuses_is_active')):
        op.drop_index(op.f('ix_redmine_statuses_is_active'), table_name='redmine_statuses')
    if _has_column('redmine_statuses', 'is_active'):
        op.drop_column('redmine_statuses', 'is_active')
