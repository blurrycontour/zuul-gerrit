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

"""zuul_time_indexes

Revision ID: 7008026b40de
Revises: 3c1488fb137e
Create Date: 2024-01-03 12:51:18.931968

"""

# revision identifiers, used by Alembic.
revision = '7008026b40de'
down_revision = '3c1488fb137e'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

BUILD_TABLE = 'zuul_build'


def upgrade(table_prefix=''):
    prefixed_build = table_prefix + BUILD_TABLE

    op.create_index(f'{prefixed_build}_timings_idx',
                    prefixed_build,
                    ['job_name', 'result', 'final', 'buildset_id'])


def downgrade():
    raise Exception("Downgrades not supported")
