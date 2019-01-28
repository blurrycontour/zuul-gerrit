# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""create retry builds table

Revision ID: 269691d2220e
Revises: e0eda5d09eae
Create Date: 2020-01-03 07:53:15.962739

"""

# revision identifiers, used by Alembic.
revision = '269691d2220e'
down_revision = '5f183546b39c'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

BUILDSET_TABLE = 'zuul_buildset'
RETRY_BUILD_TABLE = "zuul_retry_build"


def upgrade(table_prefix=''):
    op.create_table(
        table_prefix + RETRY_BUILD_TABLE,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('buildset_id', sa.Integer,
                  sa.ForeignKey(table_prefix + BUILDSET_TABLE + ".id")),
        sa.Column('uuid', sa.String(36)),
        sa.Column('job_name', sa.String(255)),
        sa.Column('result', sa.String(255)),
        sa.Column('start_time', sa.DateTime()),
        sa.Column('end_time', sa.DateTime()),
        sa.Column('voting', sa.Boolean),
        sa.Column('log_url', sa.String(255)),
        sa.Column('node_name', sa.String(255)),
    )


def downgrade():
    raise Exception("Downgrades not supported")
