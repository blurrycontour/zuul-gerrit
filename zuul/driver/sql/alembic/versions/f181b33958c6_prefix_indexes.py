# Copyright 2018 BMW Car IT GmbH
#
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

"""prefix-indexes

Revision ID: f181b33958c6
Revises: defa75d297bf
Create Date: 2018-04-10 07:51:48.918303

"""

# revision identifiers, used by Alembic.
revision = 'f181b33958c6'
down_revision = 'defa75d297bf'
branch_labels = None
depends_on = None

from alembic import op
from sqlalchemy import engine_from_config
from sqlalchemy.engine import reflection

BUILDSET_TABLE = 'zuul_buildset'
BUILD_TABLE = 'zuul_build'


def index_exists(index_name, table_name, inspector):
    indexes = inspector.get_indexes(table_name)
    for index in indexes:
        if index.get('name') == index_name:
            return True
    return False


def upgrade(table_prefix=''):
    if not table_prefix:
        return

    config = op.get_context().config
    engine = engine_from_config(
        config.get_section(config.config_ini_section), prefix='sqlalchemy.')
    inspector = reflection.Inspector.from_engine(engine)

    prefixed_buildset = table_prefix + BUILDSET_TABLE
    prefixed_build = table_prefix + BUILD_TABLE

    # We need to prefix any non-prefixed index if needed. Do this by dropping
    # and recreating the index.
    if index_exists('project_pipeline_idx', prefixed_buildset, inspector):
        op.drop_index('project_pipeline_idx', prefixed_buildset)

    if index_exists('project_change_idx', prefixed_buildset, inspector):
        op.drop_index('project_change_idx', prefixed_buildset)

    if index_exists('change_idx', prefixed_buildset, inspector):
        op.drop_index('change_idx', prefixed_buildset)

    if index_exists('job_name_buildset_id_idx', prefixed_build, inspector):
        op.drop_index('job_name_buildset_id_idx', prefixed_build)

    # To allow a dashboard to show a per-project view, optionally filtered
    # by pipeline.
    if not index_exists(table_prefix + 'project_pipeline_idx',
                        prefixed_buildset, inspector):
        op.create_index(
            table_prefix + 'project_pipeline_idx',
            prefixed_buildset, ['project', 'pipeline'])

    # To allow a dashboard to show a per-project-change view
    if not index_exists(table_prefix + 'project_change_idx',
                        prefixed_buildset, inspector):
        op.create_index(
            table_prefix + 'project_change_idx',
            prefixed_buildset, ['project', 'change'])

    # To allow a dashboard to show a per-change view
    if not index_exists(table_prefix + 'change_idx',
                        prefixed_buildset, inspector):
        op.create_index(table_prefix + 'change_idx',
                        prefixed_buildset, ['change'])

    # To allow a dashboard to show a job lib view. buildset_id is included
    # so that it's a covering index and can satisfy the join back to buildset
    # without an additional lookup.
    if not index_exists(table_prefix + 'job_name_buildset_id_idx',
                        prefixed_build, inspector):
        op.create_index(
            table_prefix + 'job_name_buildset_id_idx', prefixed_build,
            ['job_name', 'buildset_id'])


def downgrade():
    raise Exception("Downgrades not supported")
