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


def upgrade():
    build_table = context.config.get_main_option('zuul.build_table')
    build_metadata_table = build_table + '_metadata'

    op.create_table(
        build_table,
        sa.Column('uuid', sa.String(255)),
        sa.Column('job_name', sa.String(255)),
        sa.Column('score', sa.Integer),
        sa.Column('result', sa.String(255)),
        sa.Column('start_time', sa.Integer),
        sa.Column('end_time', sa.Integer),
        sa.Column('message', sa.String(255)),
        sa.UniqueConstraint(
            'uuid', 'job_name', name='zuul_build_uuid_job_name'),
    )

    op.create_table(
        build_metadata_table,
        sa.Column('build_uuid', sa.String(255)),
        sa.Column('build_job_name', sa.String(255)),
        sa.Column('key', sa.String(255)),
        sa.Column('value', sa.String(255)),
        sa.UniqueConstraint(
            'build_uuid', 'build_job_name', 'key',
            name='zuul_build_metadata_build_uuid_build_job_name_key'),
    )


def downgrade():
    build_table = context.config.get_main_option('zuul.build_table')
    build_metadata_table = build_table + '_metadata'
    op.drop_table(build_table)
    op.drop_table(build_metadata_table)
