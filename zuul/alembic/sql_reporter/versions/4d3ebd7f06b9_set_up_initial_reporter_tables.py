"""Set up initial reporter tables

Revision ID: 4d3ebd7f06b9
Revises:
Create Date: 2015-12-06 15:27:38.080020

"""

# revision identifiers, used by Alembic.
revision = '4d3ebd7f06b9'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op, context
import sqlalchemy as sa

BUILD_TABLE = 'zuul_build'
BUILD_METADATA_TABLE = BUILD_TABLE + '_metadata'


def upgrade():
    op.create_table(
        BUILD_TABLE,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('uuid', sa.String(255)),
        sa.Column('job_name', sa.String(255)),
        sa.Column('score', sa.Integer),
        sa.Column('result', sa.String(255)),
        sa.Column('start_time', sa.Integer),
        sa.Column('end_time', sa.Integer),
        sa.Column('message', sa.String(255)),
    )

    op.create_table(
        BUILD_METADATA_TABLE,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('build_id', sa.Integer, sa.ForeignKey(BUILD_TABLE + ".id")),
        sa.Column('key', sa.String(255)),
        sa.Column('value', sa.String(255)),
    )


def downgrade():
    raise Exception("Downgrades not supported")
