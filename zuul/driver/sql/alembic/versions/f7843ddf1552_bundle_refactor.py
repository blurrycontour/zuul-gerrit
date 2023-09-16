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
ARTIFACT_TABLE = 'zuul_artifact'
BUILD_EVENT_TABLE = 'zuul_build_event'
PROVIDES_TABLE = 'zuul_provides'


def mysql_unhex(x):
    return f"unhex({x})"


def mysql_int_to_bin(x):
    return f"cast({x} as unsigned)"


def pg_unhex(x):
    return f"decode({x}, 'hex')"


def pg_int_to_bin(x):
    return f"decode(lpad(to_hex(cast({x} as integer)), 40, '0'), 'hex')"


def rename_index(connection, table, old, new):
    dialect_name = connection.engine.dialect.name
    if dialect_name == 'mysql':
        statement = f"""
            alter table {table}
            rename index {old}
            to {new}
        """
    elif dialect_name == 'postgresql':
        statement = f"""
            alter index {old}
            rename to {new}
        """
    else:
        raise Exception("Unsupported dialect {dialect_name}")
    connection.execute(sa.text(statement))


def upgrade(table_prefix=''):
    prefixed_ref = table_prefix + REF_TABLE
    prefixed_build = table_prefix + BUILD_TABLE
    prefixed_build_new = table_prefix + BUILD_TABLE + '_new'
    prefixed_buildset = table_prefix + BUILDSET_TABLE
    prefixed_buildset_ref = table_prefix + BUILDSET_REF_TABLE
    prefixed_artifact = table_prefix + ARTIFACT_TABLE
    prefixed_build_event = table_prefix + BUILD_EVENT_TABLE
    prefixed_provides = table_prefix + PROVIDES_TABLE

    connection = op.get_bind()
    quote = connection.engine.dialect.identifier_preparer.quote
    dialect_name = connection.engine.dialect.name
    if dialect_name == 'mysql':
        pass
    elif dialect_name == 'postgresql':
        pass
    else:
        raise Exception("Unsupported dialect {dialect_name}")
    # Normalize data in buildset table

    # The postgres operator "is not distinct from" (equivalent to
    # mysql's <=>) is a non-indexable operator.  So that we can
    # actually use the unique index (and other indexes in the future)
    # make all of the ref-related columns non-null.  That means empty
    # strings for strings, and we'll use 0 for the change id.

    connection.execute(sa.text(
        f"""update {prefixed_buildset} set {quote('change')}=0
            where {quote('change')} is null"""
    ))
    connection.execute(sa.text(
        f"update {prefixed_buildset} set patchset='' where patchset is null"
    ))
    connection.execute(sa.text(
        f"update {prefixed_buildset} set oldrev='' where oldrev is null"
    ))
    connection.execute(sa.text(
        f"update {prefixed_buildset} set newrev='' where newrev is null"
    ))
    connection.execute(sa.text(
        f"update {prefixed_buildset} set branch='' where branch is null"
    ))
    connection.execute(sa.text(
        f"update {prefixed_buildset} set ref='' where ref is null"
    ))
    connection.execute(sa.text(
        f"update {prefixed_buildset} set ref_url='' where ref_url is null"
    ))

    # Create zuul_ref table.
    op.create_table(
        prefixed_ref,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('project', sa.String(255), nullable=False),
        sa.Column('ref', sa.String(255), nullable=False),
        sa.Column('ref_url', sa.String(255), nullable=False),
        sa.Column('change', sa.Integer, nullable=False),
        sa.Column('patchset', sa.String(40), nullable=False),
        sa.Column('oldrev', sa.String(40), nullable=False),
        sa.Column('newrev', sa.String(40), nullable=False),
        sa.Column('branch', sa.String(255), nullable=False),
    )

    # Copy data from buildset to ref

    # We are going to have a unique index later on some columns, so we
    # use a "group by" clause here to remove duplicates.  We also may
    # have differing values for ref_url for the same refs (e.g.,
    # opendev switched gerrit server hostnames), so we arbitrarily
    # take the first ref_url for a given grouping.  It doesn't make
    # sense for branch to be different, but we do the same in order to
    # avoid any potential errors.
    statement = f"""
        insert into zuul_ref
            (project, {quote('change')}, patchset,
             ref, ref_url, oldrev, newrev, branch)
        select
            bs.project, bs.change, bs.patchset,
            bs.ref, min(ref_url), bs.oldrev, bs.newrev, min(branch)
        from zuul_buildset bs
        group by
            bs.project, bs.change, bs.patchset,
            bs.ref, bs.oldrev, bs.newrev
    """
    connection.execute(sa.text(statement))

    # Create our unique ref constraint; this includes as index that
    # will speed up populating the buildset_ref table.
    op.create_unique_constraint(
        f'{prefixed_ref}_unique',
        prefixed_ref,
        ['project', 'ref', 'change', 'patchset', 'oldrev', 'newrev'],
    )

    # Create replacement indexes for the obsolete indexes on the
    # buildset table.
    with op.batch_alter_table(prefixed_ref) as batch_op:
        batch_op.create_index(
            f'{prefixed_ref}_project_change_idx',
            ['project', 'change'])
        batch_op.create_index(
            f'{prefixed_ref}_change_idx',
            ['change'])

    # Add mapping table for buildset <-> ref

    # We will add foreign key constraints after populating the table.
    op.create_table(
        prefixed_buildset_ref,
        sa.Column('buildset_id', sa.Integer, nullable=False),
        sa.Column('ref_id', sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("buildset_id", "ref_id"),
    )

    # Populate buildset_ref table.  Ignore ref_url since we don't
    # include it in the unique index later.
    statement = f"""
        insert into {prefixed_buildset_ref}
        select {prefixed_buildset}.id, {prefixed_ref}.id
        from {prefixed_buildset} left join {prefixed_ref}
        on {prefixed_buildset}.project = {prefixed_ref}.project
        and {prefixed_buildset}.ref = {prefixed_ref}.ref
        and {prefixed_buildset}.change = {prefixed_ref}.change
        and {prefixed_buildset}.patchset = {prefixed_ref}.patchset
        and {prefixed_buildset}.oldrev = {prefixed_ref}.oldrev
        and {prefixed_buildset}.newrev = {prefixed_ref}.newrev
    """
    connection.execute(sa.text(statement))

    # Now that the table is populated, add the FK indexes and
    # constraints to buildset_ref.
    op.create_index(
        f'{prefixed_buildset_ref}_buildset_id_idx',
        prefixed_buildset_ref, ['buildset_id'])
    op.create_index(
        f'{prefixed_buildset_ref}_ref_id_idx',
        prefixed_buildset_ref, ['ref_id'])
    op.create_foreign_key(
        f'{prefixed_buildset_ref}_buildset_id_fkey',
        prefixed_buildset_ref,
        prefixed_buildset,
        ['buildset_id'], ['id'])
    op.create_foreign_key(
        f'{prefixed_buildset_ref}_ref_id_fkey',
        prefixed_buildset_ref,
        prefixed_ref,
        ['ref_id'], ['id'])

    # Our goal is to add the ref_id column to the build table and
    # populate it with a query.  But in postgres, tables have a fill
    # factor which indicates how much space to leave in pages for row
    # updates.  With a high fill factor (the default is 100%) large
    # updates can be slow.  With a smaller fill factor, large updates
    # can bu much faster, at the cost of wasted space and operational
    # overhead.  The default of 100% makes sense for all of our
    # tables.  While the build and buildset tables do get some row
    # updates, they are not very frequent.  We would need a very
    # generous fill factor to be able to update all of the rows in the
    # build table quickly, and that wouldn't make sense for normal
    # operation.

    # Instead of adding the column and updating the table, we will
    # create a new table and populate it with inserts (which is
    # extremely fast), then remove the old table and rename the new.

    # Create the new table
    op.create_table(
        prefixed_build_new,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('buildset_id', sa.Integer),
        sa.Column('uuid', sa.String(36)),
        sa.Column('job_name', sa.String(255)),
        sa.Column('result', sa.String(255)),
        sa.Column('start_time', sa.DateTime),
        sa.Column('end_time', sa.DateTime),
        sa.Column('voting', sa.Boolean),
        sa.Column('log_url', sa.String(255)),
        sa.Column('error_detail', sa.TEXT()),
        sa.Column('final', sa.Boolean),
        sa.Column('held', sa.Boolean),
        sa.Column('nodeset', sa.String(255)),
        sa.Column('ref_id', sa.Integer),
    )

    statement = f"""
        insert into {prefixed_build_new}
            select
                {prefixed_build}.id,
                {prefixed_build}.buildset_id,
                {prefixed_build}.uuid,
                {prefixed_build}.job_name,
                {prefixed_build}.result,
                {prefixed_build}.start_time,
                {prefixed_build}.end_time,
                {prefixed_build}.voting,
                {prefixed_build}.log_url,
                {prefixed_build}.error_detail,
                {prefixed_build}.final,
                {prefixed_build}.held,
                {prefixed_build}.nodeset,
                {prefixed_buildset_ref}.ref_id
            from {prefixed_build} left join {prefixed_buildset}
              on {prefixed_build}.buildset_id = {prefixed_build}set.id
            left join {prefixed_buildset}_ref
              on {prefixed_buildset}_ref.buildset_id = {prefixed_buildset}.id
    """
    connection.execute(sa.text(statement))

    # Fix the sequence value since we wrote our own ids (postgres only)
    if dialect_name == 'postgresql':
        statement = f"""
            select setval(
                 '{prefixed_build_new}_id_seq',
                 COALESCE((SELECT MAX(id)+1 FROM {prefixed_build_new}), 1),
                 false)
        """
        connection.execute(sa.text(statement))

    # Add the foreign key indexes and constraits to our new table
    # first, to make sure we can before we drop the old one.
    with op.batch_alter_table(prefixed_build_new) as batch_op:
        batch_op.create_index(
            f'{prefixed_build_new}_buildset_id_idx',
            ['buildset_id'])
        batch_op.create_index(
            f'{prefixed_build_new}_ref_id_idx',
            ['ref_id'])
        batch_op.create_foreign_key(
            f'{prefixed_build_new}_buildset_id_fkey',
            prefixed_buildset,
            ['buildset_id'], ['id'])
        batch_op.create_foreign_key(
            f'{prefixed_build_new}_ref_id_fkey',
            prefixed_ref,
            ['ref_id'], ['id'])

    # Temporarily drop the FK constraints that reference the old build
    # table. (This conditional is why we're renaming all the indexes
    # and constraints to be consistent).
    if dialect_name == 'mysql':
        op.drop_constraint(table_prefix + 'zuul_artifact_ibfk_1',
                           prefixed_artifact, 'foreignkey')
        op.drop_constraint(table_prefix + 'zuul_build_event_ibfk_1',
                           prefixed_build_event, 'foreignkey')
        op.drop_constraint(table_prefix + 'zuul_provides_ibfk_1',
                           prefixed_provides, 'foreignkey')
    elif dialect_name == 'postgresql':
        op.drop_constraint(table_prefix + 'zuul_artifact_build_id_fkey',
                           prefixed_artifact)
        op.drop_constraint(table_prefix + 'zuul_build_event_build_id_fkey',
                           prefixed_build_event)
        op.drop_constraint(table_prefix + 'zuul_provides_build_id_fkey',
                           prefixed_provides)
    else:
        raise Exception("Unsupported dialect {dialect_name}")

    # Drop the old table
    op.drop_table(prefixed_build)

    # Rename the table
    op.rename_table(prefixed_build_new, prefixed_build)

    # Rename the sequence and primary key (postgres only)
    if dialect_name == 'postgresql':
        statement = f"""
            alter sequence {prefixed_build_new}_id_seq
            rename to {prefixed_build}_id_seq;
        """
        connection.execute(sa.text(statement))
        rename_index(connection, prefixed_build_new,
                     f'{prefixed_build_new}_pkey',
                     f'{prefixed_build}_pkey')

    # Replace the indexes
    with op.batch_alter_table(prefixed_build) as batch_op:
        # This used to be named job_name_buildset_id_idx, let's
        # upgrade to our new naming scheme
        batch_op.create_index(
            f'{prefixed_build}_job_name_buildset_id_idx',
            ['job_name', 'buildset_id'])
        # Previously named uuid_buildset_id_idx
        batch_op.create_index(
            f'{prefixed_build}_uuid_buildset_id_idx',
            ['uuid', 'buildset_id'])

    # Rename indexes
    rename_index(connection, prefixed_build,
                 f'{prefixed_build_new}_buildset_id_idx',
                 f'{prefixed_build}_buildset_id_idx')
    rename_index(connection, prefixed_build,
                 f'{prefixed_build_new}_ref_id_idx',
                 f'{prefixed_build}_ref_id_idx')

    # Mysql does not support renaming constraints, so we drop and
    # re-add them.  We added them earlier to confirm that there were
    # no errors before dropping the original table.
    with op.batch_alter_table(prefixed_build) as batch_op:
        batch_op.drop_constraint(
            f'{prefixed_build_new}_buildset_id_fkey',
            'foreignkey')
        batch_op.drop_constraint(
            f'{prefixed_build_new}_ref_id_fkey',
            'foreignkey')
        batch_op.create_foreign_key(
            f'{prefixed_build}_buildset_id_fkey',
            prefixed_buildset,
            ['buildset_id'], ['id'])
        batch_op.create_foreign_key(
            f'{prefixed_build}_ref_id_fkey',
            prefixed_ref,
            ['ref_id'], ['id'])

    # Re-add the referencing FK constraints
    op.create_foreign_key(
        f'{prefixed_artifact}_build_id_fkey',
        prefixed_artifact,
        prefixed_build,
        ['build_id'], ['id'])
    op.create_foreign_key(
        f'{prefixed_build_event}_build_id_fkey',
        prefixed_build_event,
        prefixed_build,
        ['build_id'], ['id'])
    op.create_foreign_key(
        f'{prefixed_provides}_build_id_fkey',
        prefixed_provides,
        prefixed_build,
        ['build_id'], ['id'])

    # Rename some indexes for a consistent naming scheme
    rename_index(connection, prefixed_artifact,
                 f'{table_prefix}artifact_build_id_idx',
                 f'{prefixed_artifact}_build_id_idx')
    rename_index(connection, prefixed_build_event,
                 f'{table_prefix}build_event_build_id_idx',
                 f'{prefixed_build_event}_build_id_idx')
    rename_index(connection, prefixed_provides,
                 f'{table_prefix}provides_build_id_idx',
                 f'{prefixed_provides}_build_id_idx')

    # Drop the obsolete buildset indexes
    with op.batch_alter_table(prefixed_buildset) as batch_op:
        batch_op.drop_index(table_prefix + 'project_pipeline_idx')
        batch_op.drop_index(table_prefix + 'project_change_idx')
        batch_op.drop_index(table_prefix + 'change_idx')

    # The zuul_ref column is not strictly related to this change, but
    # is obsolete.  Drop all the columns in one statement for
    # efficiency (alembic doesn't have a way to do this).
    statement = f"""alter table {prefixed_buildset}
        drop column project,
        drop column {quote('change')},
        drop column patchset,
        drop column ref,
        drop column ref_url,
        drop column oldrev,
        drop column newrev,
        drop column branch,
        drop column zuul_ref
    """
    connection.execute(sa.text(statement))

    # Rename indexes for consistency
    rename_index(connection, prefixed_buildset,
                 f'{table_prefix}uuid_idx',
                 f'{prefixed_buildset}_uuid_idx')


def downgrade():
    raise Exception("Downgrades not supported")
