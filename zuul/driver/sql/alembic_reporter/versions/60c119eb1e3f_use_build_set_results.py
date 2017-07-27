"""Use build_set results

Revision ID: 60c119eb1e3f
Revises: f86c9871ee67
Create Date: 2017-07-27 17:09:20.374782

"""

# revision identifiers, used by Alembic.
revision = '60c119eb1e3f'
down_revision = 'f86c9871ee67'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

BUILDSET_TABLE = 'zuul_buildset'

# Make a model that includes both columns so that we can use it for data
# translation in the migration below.
migration_helper = sa.Table(
    BUILDSET_TABLE,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('zuul_ref', sa.String(255)),
    sa.Column('pipeline', sa.String(255)),
    sa.Column('project', sa.String(255)),
    sa.Column('change', sa.Integer, nullable=True),
    sa.Column('patchset', sa.Integer, nullable=True),
    sa.Column('ref', sa.String(255)),
    sa.Column('score', sa.Integer),
    sa.Column('result', sa.String(8)),
    sa.Column('message', sa.TEXT()),
)


def upgrade():
    # SUCCESS, FAILURE, CANCELED
    op.add_column(BUILDSET_TABLE, sa.Column('result', sa.String(8)))

    connection = op.get_bind()
    for buildset in connection.execute(migration_helper.select()):
        result = 'SUCCESS' if buildset.score == 1 else 'FAILURE'
        connection.execute(
            migration_helper.update().where(
                migration_helper.c.id == buildset.id
            ).values(
                result=result
            )
        )
    op.drop_column(BUILDSET_TABLE, 'score')


def downgrade():
    op.add_column(BUILDSET_TABLE, sa.Column('score', sa.Integer))

    connection = op.get_bind()
    for buildset in connection.execute(migration_helper.select()):
        score = 1 if buildset.result == 'SUCCESS' else -1
        connection.execute(
            migration_helper.update().where(
                migration_helper.c.id == buildset.id
            ).values(
                score=score
            )
        )
    op.drop_column(BUILDSET_TABLE, 'result')
