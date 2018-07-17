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

"""Add default url column

Revision ID: 1a84e33223d2
Revises: f181b33958c6
Create Date: 2018-07-17 00:10:18.822434

"""

# revision identifiers, used by Alembic.
revision = '1a84e33223d2'
down_revision = 'f181b33958c6'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade(table_prefix=''):
    op.add_column(
        table_prefix + 'zuul_build', sa.Column('default_url', sa.String(255)))


def downgrade():
    raise Exception("Downgrades not supported")
