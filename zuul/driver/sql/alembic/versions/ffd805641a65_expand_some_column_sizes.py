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

"""Expand some column sizes

Revision ID: ffd805641a65
Revises: 6c1582c1d08c
Create Date: 2024-12-18 19:06:19.857887

"""

# revision identifiers, used by Alembic.
revision = 'ffd805641a65'
down_revision = '6c1582c1d08c'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from zuul.model import MAX_LENGTH_MAP


BUILDSET_TABLE = 'zuul_buildset'
REF_TABLE = 'zuul_ref'
BUILD_TABLE = 'zuul_build'
ARTIFACT_TABLE = 'zuul_artifact'
PROVIDES_TABLE = 'zuul_provides'


def upgrade(table_prefix=''):
    op.alter_column(table_prefix + REF_TABLE,
                    'project',
                    type_=sa.String(MAX_LENGTH_MAP["PROJECT_NAME"]),
                    existing_nullable=True)
    op.alter_column(table_prefix + REF_TABLE,
                    'ref_url',
                    type_=sa.TEXT(),
                    existing_nullable=True)

    op.alter_column(table_prefix + BUILDSET_TABLE,
                    'pipeline',
                    type_=sa.String(MAX_LENGTH_MAP["PIPELINE_NAME"]),
                    existing_nullable=True)
    op.alter_column(table_prefix + BUILDSET_TABLE,
                    'tenant',
                    type_=sa.String(MAX_LENGTH_MAP["TENANT_NAME"]),
                    existing_nullable=True)

    op.alter_column(table_prefix + BUILD_TABLE,
                    'job_name',
                    type_=sa.String(MAX_LENGTH_MAP["JOB_NAME"]),
                    existing_nullable=True)
    op.alter_column(table_prefix + BUILD_TABLE,
                    'log_url',
                    type_=sa.TEXT(),
                    existing_nullable=True)
    op.alter_column(table_prefix + BUILD_TABLE,
                    'nodeset',
                    type_=sa.TEXT(),
                    existing_nullable=True)

    op.alter_column(table_prefix + ARTIFACT_TABLE,
                    'name',
                    type_=sa.String(MAX_LENGTH_MAP["ARTIFACT_NAME"]),
                    existing_nullable=True)

    op.alter_column(table_prefix + PROVIDES_TABLE,
                    'name',
                    type_=sa.String(MAX_LENGTH_MAP["PROVIDES_NAME"]),
                    existing_nullable=True)

def downgrade():
    raise Exception("Downgrades not supported")
