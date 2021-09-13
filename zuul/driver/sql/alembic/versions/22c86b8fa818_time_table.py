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

"""time_table

Revision ID: 22c86b8fa818
Revises: 40c49b6fc2e3
Create Date: 2021-09-17 14:39:22.974763

"""

# revision identifiers, used by Alembic.
revision = '22c86b8fa818'
down_revision = '40c49b6fc2e3'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


TIME_TABLE = 'zuul_time'


def upgrade(table_prefix=''):
    op.create_table(
        table_prefix + TIME_TABLE,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(255)),
        sa.Column('tenant', sa.String(255)),
        sa.Column('project', sa.String(255)),
        sa.Column('branch', sa.String(255)),
        sa.Column('job_name', sa.String(255)),
        sa.Column('last_updated', sa.DateTime),
        sa.Column('t0', sa.Integer),
        sa.Column('t1', sa.Integer),
        sa.Column('t2', sa.Integer),
        sa.Column('t3', sa.Integer),
        sa.Column('t4', sa.Integer),
        sa.Column('t5', sa.Integer),
        sa.Column('t6', sa.Integer),
        sa.Column('t7', sa.Integer),
        sa.Column('t8', sa.Integer),
        sa.Column('t9', sa.Integer),
        sa.UniqueConstraint('tenant', 'project', 'branch', 'job_name'),
    )


def downgrade():
    raise Exception("Downgrades not supported")
