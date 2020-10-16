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

"""index artifacts

Revision ID: 2efbc9f6ef43
Revises: 52d49e1bfe22
Create Date: 2020-10-16 16:38:55.389688

"""

# revision identifiers, used by Alembic.
revision = '2efbc9f6ef43'
down_revision = '52d49e1bfe22'
branch_labels = None
depends_on = None

from alembic import op

ARTIFACT_TABLE = 'zuul_artifact'


def upgrade(table_prefix=''):
    prefixed_artifact = table_prefix + ARTIFACT_TABLE

    op.create_index(
        table_prefix + 'artifact_build_id_index', prefixed_artifact,
        ['build_id']
    )


def downgrade():
    raise Exception("Downgrades not supported")
