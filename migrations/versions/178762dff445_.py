"""empty message

Revision ID: 178762dff445
Revises: 12f9dcc2e36c
Create Date: 2015-03-26 11:02:49.934915

"""

# revision identifiers, used by Alembic.
revision = '178762dff445'
down_revision = '12f9dcc2e36c'

from alembic import op
from sqlalchemy.sql import table, column
from sqlalchemy import String, Boolean
import sqlalchemy as sa

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('frameworks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('expired', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    frameworks = table('frameworks',
        column('name', String),
        column('expired', Boolean)
    )

    op.execute(
        frameworks.insert(). \
        values({'name': op.inline_literal('G-Cloud 6'), 'expired': op.inline_literal(False)})
    )


    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('frameworks')
    ### end Alembic commands ###
