"""Add countersigned fields to FrameworkAgreement

Revision ID: 730
Revises: 720
Create Date: 2016-09-01 12:02:16.236692

"""

# revision identifiers, used by Alembic.
revision = '730'
down_revision = '720'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.add_column('framework_agreements', sa.Column('countersigned_agreement_details', postgresql.JSON(), nullable=True))
    op.add_column('framework_agreements', sa.Column('countersigned_agreement_path', sa.String(), nullable=True))
    op.add_column('framework_agreements', sa.Column('countersigned_agreement_returned_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('framework_agreements', 'countersigned_agreement_returned_at')
    op.drop_column('framework_agreements', 'countersigned_agreement_path')
    op.drop_column('framework_agreements', 'countersigned_agreement_details')
