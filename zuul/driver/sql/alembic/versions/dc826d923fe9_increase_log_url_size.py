"""increase log_url size

Revision ID: dc826d923fe9
Revises: 6c1582c1d08c
Create Date: 2024-08-21 15:20:17.997249

"""

# revision identifiers, used by Alembic.
revision = 'dc826d923fe9'
down_revision = '6c1582c1d08c'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

BUILD_TABLE = 'zuul_build'


def upgrade(table_prefix=''):
    op.alter_column(table_prefix + BUILD_TABLE,
                    'log_url',
                    type_=sa.TEXT(),
                    existing_nullable=True,
                    existing_type=sa.String(255))


def downgrade():
    raise Exception("Downgrades not supported")
