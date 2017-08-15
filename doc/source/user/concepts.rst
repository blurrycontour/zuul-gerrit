:title: Zuul Concepts

Zuul Concepts
=============

Zuul's configuration is organized around the concept of a *pipeline*.
An example pipeline, defined in the Zuul configuration file, might
look similar to the following (see the :ref:`pipeline` section for
a more detailed discussion on pipeline configuration):

.. code-block:: yaml

   - pipeline:
       name: check
       manager: independent
       trigger:
         my_gerrit:
           - event: patchset-created
       success:
         my_gerrit:
           Verified: 1
       failure:
         my_gerrit
           Verified: -1

In Zuul, a pipeline encompasses a workflow process which can be
applied to one or more projects.  For instance, a "check" pipeline
might describe the actions which should cause newly proposed changes
to projects to be tested.  A "gate" pipeline might implement
:ref:`project_gating` to automate merging changes to projects only if
their tests pass.  A "post" pipeline might update published
documentation for a project when changes land.

The names "check", "gate", and "post" are arbitrary -- these are not
concepts built into Zuul, but rather they are just a few common
examples of workflow processes that can be described to Zuul and
implemented as pipelines.

Once a pipeline has been defined, any number of projects may be
associated with it, each one specifying what jobs should be run for
that project in a given pipeline.

For example, a project, which we'll arbitrarily call "simple",
associated with the example pipeline above that we named "check", would
look like:

.. code-block:: yaml

    - project:
        name: simple
        check:
          jobs:
            - test-job

Project definitions are discussed in more detail in the :ref:`project`
section.

Pipelines have associated *triggers* which are descriptions of events
which should cause something to be enqueued into a pipeline.  For
example, when a patchset is uploaded to Gerrit, a Gerrit
*patchset-created* event is emitted.  A pipeline configured to trigger
on *patchset-created* events would then enqueue the associated change
when Zuul receives that event.  If there are jobs associated with that
project and pipeline, they will be run.  In addition to Gerrit, other
triggers are available, including GitHub, timer, and zuul.  See
:ref:`drivers` for a full list of available triggers.

Once all of the jobs for an item in a pipeline have been run, the
pipeline's *reporters* are responsible for reporting the results of
all of the jobs.  Continuing the example from earlier, if a pipeline
were configured with a Gerrit reporter, it would leave a review
comment on the change and set any approval votes that are configured.
There are several reporting phases available; each of which may be
configured with any number of reporters.  See :ref:`drivers` for a
full list of available reporters.

The items enqueued into a pipeline are each associated with a
`git ref <https://git-scm.com/book/en/v2/Git-Internals-Git-References>`_.
That ref may point to a proposed change, or it may be the tip of a
branch or a tag.  The triggering event determines the ref, and whether
it represents a proposed or merged commit.  Zuul prepares the ref for
an item before running jobs.  In the case of a proposed change, that
means speculatively merging the change into its target branch.  This
means that any jobs that operate on the change will run with the git
repo in the state it will be in after the change merges (which may be
substantially different than the git repo state of the change itself
since the repo may have merged other changes since the change was
originally authored).  Items in a pipeline may depend on other items,
and if they do, all of their dependent changes will be included in the
git repo state that Zuul prepares.  For more detail on this process,
see :ref:`project_gating` and :ref:`dependencies`.

The configuration for nearly everything described above is held in
files inside of the git repos upon which Zuul operates.  Zuul's
configuration is global, but distributed.  Jobs which are defined in
one project might be used in another project while pipelines are
available to all projects.  When Zuul starts, it reads its
configuration from all of the projects it knows about, and when
changes to its configuration are proposed, those changes may take
effect temporarily as part of the proposed change, or immediately
after the change merges, depending on the type of project in which the
change appears.

Jobs specify the type and quantity of nodes which they require.
Before executing each job, Zuul will contact its companion program,
Nodepool, to supply them.  Nodepool may be configured to supply static
nodes or contact cloud providers to create or delete nodes as
necessary.  The types of nodes available to Zuul are determined by the
Nodepool administrator.

Continuing our "simple" example project above, and assuming our
Nodepool adminstrator has defined an "ubuntu-xenial" node type for us,
the "test-job" referenced in the project definition might look like:

.. code-block:: yaml

    - job:
        parent: base
        name: test-job
        nodes:
           - name: test-node
             label: ubuntu-xenial

Job definitions are discussed in more detail in the :ref:`job` section.

The executable contents of jobs themselves are Ansible playbooks.
Ansible's support for orchestrating tasks on remote nodes is
particularly suited to Zuul's support for multi-node testing.  Ansible
is also easy to use for simple tasks (such as executing a shell
script) or sophisticated deployment scenarios.  When Zuul runs
Ansible, it attempts to do so in a manner most similar to the way that
Ansible might be used to orchestrate remote systems.  Ansible itself
is run on the :ref:`executor <executor>` and acts remotely upon the test
nodes supplied to a job.  This facilitates continuous delivery by making it
possible to use the same Ansible playbooks in testing and production.

Furthering our "simple" example project, we could have a playbook to execute
on the test node, which we've cleverly named "test-node" in our job definition
above, that might look like:

.. code-block:: yaml

    ---
    - hosts: test-node
      tasks:
          - name: Run PEP8 check
            command: tox -e pep8
            args:
                chdir: "src/{{ zuul.project.canonical_name }}"

Job content is discussed in more detail in the :doc:`Job Content <jobs>`
page.
