"""Imported body meshes

Revision ID: c41d2a7e9b10
Revises: be5f085359d7
Create Date: 2026-09-30 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c41d2a7e9b10'
down_revision: Union[str, Sequence[str], None] = 'be5f085359d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('body_meshes',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('owner_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('info', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('triangles', sa.LargeBinary(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('body_meshes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_body_meshes_owner_id'), ['owner_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('body_meshes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_body_meshes_owner_id'))
    op.drop_table('body_meshes')
