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

"""zuul_trigger_ref

Revision ID: 4c050a0c0139
Revises: ac1dad8c9434
Create Date: 2024-03-12 13:14:58.331308

"""

# revision identifiers, used by Alembic.
revision = '4c050a0c0139'
down_revision = 'ac1dad8c9434'
branch_labels = None
depends_on = None

REF_TABLE = 'zuul_ref'

from alembic import op
import sqlalchemy as sa


def upgrade(table_prefix=''):
    op.add_column(
        table_prefix + "zuul_buildset",
        sa.Column("event_ref_id",
                  sa.Integer, sa.ForeignKey(
                      table_prefix + REF_TABLE + ".id",
                      name=table_prefix + 'zuul_buildset_event_ref_id_fkey')))


def downgrade():
    raise Exception("Downgrades not supported")
