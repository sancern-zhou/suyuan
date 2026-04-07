"""remove session state

Revision ID: remove_session_state
Revises:
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_session_state'
down_revision = 'add_knowledge_conversation'  # 根据你的最新迁移调整
branch_labels = None
depends_on = None


def upgrade():
    """删除 state 列"""
    # 删除索引（如果存在）
    try:
        op.drop_index('ix_sessions_state_created', table_name='sessions')
    except Exception:
        pass

    # 删除 state 列
    op.drop_column('sessions', 'state')


def downgrade():
    """恢复 state 列（回滚）"""
    # 添加 state 列
    op.add_column(
        'sessions',
        sa.Column(
            'state',
            sa.Enum('active', 'paused', 'completed', 'failed', 'archived', name='sessionstate'),
            nullable=False,
            server_default='active'
        )
    )

    # 创建索引
    op.create_index(
        'ix_sessions_state_created',
        'sessions',
        ['state', 'created_at']
    )
