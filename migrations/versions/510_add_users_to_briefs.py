"""Add users to briefs

Revision ID: 510
Revises: 500
Create Date: 2016-01-25 17:08:03.550222

"""

# revision identifiers, used by Alembic.
revision = '510'
down_revision = '500'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('brief_users',
    sa.Column('brief_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['brief_id'], ['briefs.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('brief_id', 'user_id')
    )


def downgrade():
    op.drop_table('brief_users')
