# Copyright 2023 Acme Gating, LLC
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

"""bundle_refactor

Revision ID: f7843ddf1552
Revises: 151893067f91
Create Date: 2023-09-16 09:25:00.674820

"""

# revision identifiers, used by Alembic.
revision = 'f7843ddf1552'
down_revision = '151893067f91'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


REF_TABLE = 'zuul_ref'
BUILD_TABLE = 'zuul_build'
BUILDSET_TABLE = 'zuul_buildset'
BUILDSET_REF_TABLE = 'zuul_buildset_ref'


def upgrade(table_prefix=''):
    prefixed_ref = table_prefix + REF_TABLE
    prefixed_build = table_prefix + BUILD_TABLE
    prefixed_buildset = table_prefix + BUILDSET_TABLE
    prefixed_buildset_ref = table_prefix + BUILDSET_REF_TABLE

    # Create zuul_ref table
    op.create_table(
        prefixed_ref,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('project', sa.String(255)),
        sa.Column('change', sa.Integer, nullable=True),
        sa.Column('patchset', sa.String(255), nullable=True),
        sa.Column('ref', sa.String(255)),
        sa.Column('ref_url', sa.String(255)),
        sa.Column('oldrev', sa.String(255)),
        sa.Column('newrev', sa.String(255)),
        sa.Column('branch', sa.String(255)),
    )
    op.create_index(
        table_prefix + 'project_change_idx', prefixed_ref,
        ['project', 'change'])
    op.create_index(
        table_prefix + 'change_idx', prefixed_ref,
        ['change'])

    # Add mapping table for buildset <-> ref
    op.create_table(
        prefixed_buildset_ref,
        sa.Column('buildset_id', sa.Integer,
                  sa.ForeignKey(
                      prefixed_buildset + ".id")),
        sa.Column('ref_id', sa.Integer,
                  sa.ForeignKey(
                      prefixed_ref + ".id")),
        sa.PrimaryKeyConstraint("buildset_id", "ref_id"),
    )
    op.create_index(
        table_prefix + 'buildset_ref_buildset_id_idx',
        prefixed_buildset_ref, ['buildset_id'])
    op.create_index(
        table_prefix + 'buildset_ref_ref_id_idx',
        prefixed_buildset_ref, ['ref_id'])

    # Copy data from buildset to ref
    connection = op.get_bind()
    query = f"""
        insert into {prefixed_ref}
            (project, `change`, patchset, ref, ref_url, oldrev, newrev)
        select distinct
            project, `change`, patchset, ref, ref_url, oldrev, newrev
        from {prefixed_buildset}"""
    connection.execute(sa.text(query))

    # Populate buildset_ref table
    query = f"""
        insert into {prefixed_buildset_ref}
        select {prefixed_buildset}.id, {prefixed_ref}.id
        from {prefixed_buildset}, {prefixed_ref}
        where ({prefixed_buildset}.project = {prefixed_ref}.project
               or ({prefixed_buildset}.project is null
                   and {prefixed_ref}.project is null))
        and ({prefixed_buildset}.change = {prefixed_ref}.change
             or ({prefixed_buildset}.change is null
                 and {prefixed_ref}.change is null))
        and ({prefixed_buildset}.patchset = {prefixed_ref}.patchset
             or ({prefixed_buildset}.patchset is null
                 and {prefixed_ref}.patchset is null))
        and ({prefixed_buildset}.ref = {prefixed_ref}.ref
             or ({prefixed_buildset}.ref is null
                 and {prefixed_ref}.ref is null))
        and ({prefixed_buildset}.ref_url = {prefixed_ref}.ref_url
             or ({prefixed_buildset}.ref_url is null
                 and {prefixed_ref}.ref_url is null))
        and ({prefixed_buildset}.oldrev = {prefixed_ref}.oldrev
             or ({prefixed_buildset}.oldrev is null
                 and {prefixed_ref}.oldrev is null))
        and ({prefixed_buildset}.newrev = {prefixed_ref}.newrev
             or ({prefixed_buildset}.newrev is null
                 and {prefixed_ref}.newrev is null))
    """
    connection.execute(sa.text(query))

    # Add the ref_id column to the build table
    op.add_column(
        prefixed_build,
        sa.Column('ref_id', sa.Integer, sa.ForeignKey(
            prefixed_ref + ".id"))
    )
    op.create_index(
        table_prefix + 'build_ref_id_idx',
        prefixed_build, ['ref_id'])

    # Link all builds to their buildset's ref
    query = f"""
        update {prefixed_build}
        inner join {prefixed_buildset}
          on {prefixed_build}.buildset_id = {prefixed_buildset}.id
        inner join {prefixed_buildset_ref}
          on {prefixed_buildset_ref}.buildset_id = {prefixed_buildset}.id
        set {prefixed_build}.ref_id = {prefixed_buildset_ref}.ref_id
    """
    connection.execute(sa.text(query))

    # Drop the obsolete buildset indexes and columns
    with op.batch_alter_table(prefixed_buildset) as batch_op:
        batch_op.drop_index('project_pipeline_idx')
        batch_op.drop_index('project_change_idx')
        batch_op.drop_index('change_idx')
        batch_op.drop_column('project')
        batch_op.drop_column('change')
        batch_op.drop_column('patchset')
        batch_op.drop_column('ref')
        batch_op.drop_column('ref_url')
        batch_op.drop_column('oldrev')
        batch_op.drop_column('newrev')
        batch_op.drop_column('branch')
        # This is not strictly related to this change, but is obsolete
        batch_op.drop_column('zuul_ref')


def downgrade():
    raise Exception("Downgrades not supported")
