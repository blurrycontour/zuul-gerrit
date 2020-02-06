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

"""modify_buildset_message_type

Revision ID: 20b214389790
Revises: 5f183546b39c
Create Date: 2020-02-06 15:05:57.020711

"""

# revision identifiers, used by Alembic.
revision = '20b214389790'
down_revision = '5f183546b39c'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

BUILDSET_TABLE = 'zuul_buildset'


def upgrade(table_prefix=''):
    op.alter_column(table_prefix + BUILDSET_TABLE,
                    'message',
                    type_=sa.MEDIUMTEXT())


def downgrade():
    raise Exception("Downgrades not supported")
