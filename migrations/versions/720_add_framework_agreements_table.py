"""Add framework agreements table

Revision ID: 720
Revises: 710
Create Date: 2016-08-31 11:33:59.382347

"""

# revision identifiers, used by Alembic.
revision = '720'
down_revision = '710'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('framework_agreements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=False),
    sa.Column('framework_id', sa.Integer(), nullable=False),
    sa.Column('signed_agreement_returned_at', sa.DateTime(), nullable=True),
    sa.Column('signed_agreement_details', postgresql.JSON(), nullable=True),
    sa.Column('signed_agreement_path', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['supplier_id', 'framework_id'], [u'supplier_frameworks.supplier_id', u'supplier_frameworks.framework_id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('framework_agreements')
