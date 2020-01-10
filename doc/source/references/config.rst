:title: Project Configuration

.. _project-config:

Project Configuration
=====================

The following sections describe the main part of Zuul's configuration.
All of what follows is found within files inside of the repositories
that Zuul manages.

Security Contexts
-----------------

When a system administrator configures Zuul to operate on a project,
they specify one of two security contexts for that project.  A
*config-project* is one which is primarily tasked with holding
configuration information and job content for Zuul.  Jobs which are
defined in a config-project are run with elevated privileges, and all
Zuul configuration items are available for use.  Base jobs (that is,
jobs without a parent) may only be defined in config-projects.  It is
expected that changes to config-projects will undergo careful scrutiny
before being merged.

An *untrusted-project* is a project whose primary focus is not to
operate Zuul, but rather it is one of the projects being tested or
deployed.  The Zuul configuration language available to these projects
is somewhat restricted (as detailed in individual sections below), and
jobs defined in these projects run in a restricted execution
environment since they may be operating on changes which have not yet
undergone review.

Configuration Loading
---------------------

When Zuul starts, it examines all of the git repositories which are
specified by the system administrator in :ref:`tenant-config` and
searches for files in the root of each repository. Zuul looks first
for a file named ``zuul.yaml`` or a directory named ``zuul.d``, and if
they are not found, ``.zuul.yaml`` or ``.zuul.d`` (with a leading
dot). In the case of an :term:`untrusted-project`, the configuration
from every branch is included, however, in the case of a
:term:`config-project`, only the ``master`` branch is examined.

When a change is proposed to one of these files in an
untrusted-project, the configuration proposed in the change is merged
into the running configuration so that any changes to Zuul's
configuration are self-testing as part of that change.  If there is a
configuration error, no jobs will be run and the error will be
reported by any applicable pipelines.  In the case of a change to a
config-project, the new configuration is parsed and examined for
errors, but the new configuration is not used in testing the change.
This is because configuration in config-projects is able to access
elevated privileges and should always be reviewed before being merged.

As soon as a change containing a Zuul configuration change merges to
any Zuul-managed repository, the new configuration takes effect
immediately.

.. _configuration-items:

Configuration Items
-------------------

The ``zuul.yaml`` and ``.zuul.yaml`` configuration files are
YAML-formatted and are structured as a series of items, each of which
is described below.

In the case of a ``zuul.d`` (or ``.zuul.d``) directory, Zuul recurses
the directory and extends the configuration using all the .yaml files
in the sorted path order.  For example, to keep job's variants in a
separate file, it needs to be loaded after the main entries, for
example using number prefixes in file's names::

* zuul.d/pipelines.yaml
* zuul.d/projects.yaml
* zuul.d/01_jobs.yaml
* zuul.d/02_jobs-variants.yaml

.. _pipeline:

Pipeline
~~~~~~~~

A pipeline describes a workflow operation in Zuul.  It associates jobs
for a given project with triggering and reporting events.

Its flexible configuration allows for characterizing any number of
workflows, and by specifying each as a named configuration, makes it
easy to apply similar workflow operations to projects or groups of
projects.

By way of example, one of the primary uses of Zuul is to perform
project gating.  To do so, one can create a :term:`gate` pipeline
which tells Zuul that when a certain event (such as approval by a code
reviewer) occurs, the corresponding change or pull request should be
enqueued into the pipeline.  When that happens, the jobs which have
been configured to run for that project in the gate pipeline are run,
and when they complete, the pipeline reports the results to the user.

Pipeline configuration items may only appear in :term:`config-projects
<config-project>`.

Generally, a Zuul administrator would define a small number of
pipelines which represent the workflow processes used in their
environment.  Each project can then be added to the available
pipelines as appropriate.

Here is an example :term:`check` pipeline, which runs whenever a new
patchset is created in Gerrit.  If the associated jobs all report
success, the pipeline reports back to Gerrit with ``Verified`` vote of
+1, or if at least one of them fails, a -1:

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
         my_gerrit:
           Verified: -1

.. TODO: See TODO for more annotated examples of common pipeline configurations.

See :doc:`pipeline_def` for more information.

.. _job:

Job
~~~

A job is a unit of work performed by Zuul on an item enqueued into a
pipeline.  Items may run any number of jobs (which may depend on each
other).  Each job is an invocation of an Ansible playbook with a
specific inventory of hosts.  The actual tasks that are run by the job
appear in the playbook for that job while the attributes that appear in the
Zuul configuration specify information about when, where, and how the
job should be run.

Jobs in Zuul support inheritance.  Any job may specify a single parent
job, and any attributes not set on the child job are collected from
the parent job.  In this way, a configuration structure may be built
starting with very basic jobs which describe characteristics that all
jobs on the system should have, progressing through stages of
specialization before arriving at a particular job.  A job may inherit
from any other job in any project (however, if the other job is marked
as :attr:`job.final`, jobs may not inherit from it).

A job with no parent is called a *base job* and may only be defined in
a :term:`config-project`.  Every other job must have a parent, and so
ultimately, all jobs must have an inheritance path which terminates at
a base job.  Each tenant has a default parent job which will be used
if no explicit parent is specified.

Multiple job definitions with the same name are called variants.
These may have different selection criteria which indicate to Zuul
that, for instance, the job should behave differently on a different
git branch.  Unlike inheritance, all job variants must be defined in
the same project.  Some attributes of jobs marked :attr:`job.final`
may not be overridden.

When Zuul decides to run a job, it performs a process known as
freezing the job.  Because any number of job variants may be
applicable, Zuul collects all of the matching variants and applies
them in the order they appeared in the configuration.  The resulting
frozen job is built from attributes gathered from all of the
matching variants.  In this way, exactly what is run is dependent on
the pipeline, project, branch, and content of the item.

In addition to the job's main playbook, each job may specify one or
more pre- and post-playbooks.  These are run, in order, before and
after (respectively) the main playbook.  They may be used to set up
and tear down resources needed by the main playbook.  When combined
with inheritance, they provide powerful tools for job construction.  A
job only has a single main playbook, and when inheriting from a
parent, the child's main playbook overrides (or replaces) the
parent's.  However, the pre- and post-playbooks are appended and
prepended in a nesting fashion.  So if a parent job and child job both
specified pre and post playbooks, the sequence of playbooks run would
be:

* parent pre-run playbook
* child pre-run playbook
* child playbook
* child post-run playbook
* parent post-run playbook

Further inheritance would nest even deeper.

Here is an example of two job definitions:

.. code-block:: yaml

   - job:
       name: base
       pre-run: copy-git-repos
       post-run: copy-logs

   - job:
       name: run-tests
       parent: base
       nodeset:
         nodes:
           - name: test-node
             label: fedora

See :doc:`job_def` for more information.

.. _project:

Project
~~~~~~~

A project corresponds to a source code repository with which Zuul is
configured to interact.  The main responsibility of the project
configuration item is to specify which jobs should run in which
pipelines for a given project.  Within each project definition, a
section for each :ref:`pipeline <pipeline>` may appear.  This
project-pipeline definition is what determines how a project
participates in a pipeline.

Multiple project definitions may appear for the same project (for
example, in a central :term:`config projects <config-project>` as well
as in a repo's own ``.zuul.yaml``).  In this case, all of the project
definitions for the relevant branch are combined (the jobs listed in
all of the matching definitions will be run).  If a project definition
appears in a :term:`config-project`, it will apply to all branches of
the project.  If it appears in a branch of an
:term:`untrusted-project` it will only apply to changes on that
branch.  In the case of an item which does not have a branch (for
example, a tag), all of the project definitions will be combined.

Consider the following project definition::

  - project:
      name: yoyodyne
      check:
        jobs:
          - check-syntax
          - unit-tests
      gate:
        queue: integrated
        jobs:
          - unit-tests
          - integration-tests

The project has two project-pipeline stanzas, one for the ``check``
pipeline, and one for ``gate``.  Each specifies which jobs should run
when a change for that project enters the respective pipeline -- when
a change enters ``check``, the ``check-syntax`` and ``unit-test`` jobs
are run.

Pipelines which use the dependent pipeline manager (e.g., the ``gate``
example shown earlier) maintain separate queues for groups of
projects.  When Zuul serializes a set of changes which represent
future potential project states, it must know about all of the
projects within Zuul which may have an effect on the outcome of the
jobs it runs.  If project *A* uses project *B* as a library, then Zuul
must be told about that relationship so that it knows to serialize
changes to A and B together, so that it does not merge a change to B
while it is testing a change to A.

Zuul could simply assume that all projects are related, or even infer
relationships by which projects a job indicates it uses, however, in a
large system that would become unwieldy very quickly, and
unnecessarily delay changes to unrelated projects.  To allow for
flexibility in the construction of groups of related projects, the
change queues used by dependent pipeline managers are specified
manually.  To group two or more related projects into a shared queue
for a dependent pipeline, set the ``queue`` parameter to the same
value for those projects.

The ``gate`` project-pipeline definition above specifies that this
project participates in the ``integrated`` shared queue for that
pipeline.

See :doc:`project_def` for more information.

.. _project-template:

Project Template
~~~~~~~~~~~~~~~~

A Project Template defines one or more project-pipeline definitions
which can be re-used by multiple projects.

A Project Template uses the same syntax as a :ref:`project`
definition, however, in the case of a template, the
:attr:`project.name` attribute does not refer to the name of a
project, but rather names the template so that it can be referenced in
a :ref:`project` definition.

Because Project Templates may be used outside of the projects where
they are defined, they honor the implied branch :ref:`pragmas <pragma>`
(unlike Projects).  The same heuristics described in
:attr:`job.branches` that determine what implied branches a :ref:`job`
will receive apply to Project Templates (with the exception that it is
not possible to explicity set a branch matcher on a Project Template).

.. _secret:

Secret
~~~~~~

A Secret is a collection of private data for use by one or more jobs.
In order to maintain the security of the data, the values are usually
encrypted, however, data which are not sensitive may be provided
unencrypted as well for convenience.

A Secret may only be used by jobs defined within the same project.
Note that they can be used by any branch of that project, so if a
project's branches have different access controls, consider whether
all branches of that project are equally trusted before using secrets.

To use a secret, a :ref:`job` must specify the secret in
:attr:`job.secrets`.  With one exception, secrets are bound to the
playbooks associated with the specific job definition where they were
declared.  Additional pre or post playbooks which appear in child jobs
will not have access to the secrets, nor will playbooks which override
the main playbook (if any) of the job which declared the secret.  This
protects against jobs in other repositories declaring a job with a
secret as a parent and then exposing that secret.

The exception to the above is if the
:attr:`job.secrets.pass-to-parent` attribute is set to true.  In that
case, the secret is made available not only to the playbooks in the
current job definition, but to all playbooks in all parent jobs as
well.  This allows for jobs which are designed to work with secrets
while leaving it up to child jobs to actually supply the secret.  Use
this option with care, as it may allow the authors of parent jobs to
accidentially or intentionally expose secrets.  If a secret with
`pass-to-parent` set in a child job has the same name as a secret
available to a parent job's playbook, the secret in the child job will
not override the parent, instead it will simply not be available to
that playbook (but will remain available to others).

It is possible to use secrets for jobs defined in :term:`config
projects <config-project>` as well as :term:`untrusted projects
<untrusted-project>`, however their use differs slightly.  Because
playbooks in a config project which use secrets run in the
:term:`trusted execution context` where proposed changes are not used
in executing jobs, it is safe for those secrets to be used in all
types of pipelines.  However, because playbooks defined in an
untrusted project are run in the :term:`untrusted execution context`
where proposed changes are used in job execution, it is dangerous to
allow those secrets to be used in pipelines which are used to execute
proposed but unreviewed changes.  By default, pipelines are considered
`pre-review` and will refuse to run jobs which have playbooks that use
secrets in the untrusted execution context (including those subject to
:attr:`job.secrets.pass-to-parent` secrets) in order to protect
against someone proposing a change which exposes a secret.  To permit
this (for instance, in a pipeline which only runs after code review),
the :attr:`pipeline.post-review` attribute may be explicitly set to
``true``.

In some cases, it may be desirable to prevent a job which is defined
in a config project from running in a pre-review pipeline (e.g., a job
used to publish an artifact).  In these cases, the
:attr:`job.post-review` attribute may be explicitly set to ``true`` to
indicate the job should only run in post-review pipelines.

If a job with secrets is unsafe to be used by other projects, the
:attr:`job.allowed-projects` attribute can be used to restrict the
projects which can invoke that job.  If a job with secrets is defined
in an `untrusted-project`, `allowed-projects` is automatically set to
that project only, and can not be overridden (though a
:term:`config-project` may still add the job to any project's pipeline
regardless of this setting; do so with caution as other projects may
expose the source project's secrets).

Secrets, like most configuration items, are unique within a tenant,
though a secret may be defined on multiple branches of the same
project as long as the contents are the same.  This is to aid in
branch maintenance, so that creating a new branch based on an existing
branch will not immediately produce a configuration error.

See :doc:`secret_def` for more information.

.. _nodeset:

Nodeset
~~~~~~~

A Nodeset is a named collection of nodes for use by a job.  Jobs may
specify what nodes they require individually, however, by defining
groups of node types once and referring to them by name, job
configuration may be simplified.

Nodesets, like most configuration items, are unique within a tenant,
though a nodeset may be defined on multiple branches of the same
project as long as the contents are the same.  This is to aid in
branch maintenance, so that creating a new branch based on an existing
branch will not immediately produce a configuration error.

.. code-block:: yaml

   - nodeset:
       name: nodeset1
       nodes:
         - name: controller
           label: controller-label
         - name: compute1
           label: compute-label
         - name:
             - compute2
             - web
           label: compute-label
       groups:
         - name: ceph-osd
           nodes:
             - controller
         - name: ceph-monitor
           nodes:
             - controller
             - compute1
             - compute2
          - name: ceph-web
            nodes:
              - web

See :doc:`nodeset_def` for more information.

.. _semaphore:

Semaphore
~~~~~~~~~

Semaphores can be used to restrict the number of certain jobs which
are running at the same time.  This may be useful for jobs which
access shared or limited resources.  A semaphore has a value which
represents the maximum number of jobs which use that semaphore at the
same time.

Semaphores, like most configuration items, are unique within a tenant,
though a semaphore may be defined on multiple branches of the same
project as long as the value is the same.  This is to aid in branch
maintenance, so that creating a new branch based on an existing branch
will not immediately produce a configuration error.

Semaphores are never subject to dynamic reconfiguration.  If the value
of a semaphore is changed, it will take effect only when the change
where it is updated is merged.  However, Zuul will attempt to validate
the configuration of semaphores in proposed updates, even if they
aren't used.

An example usage of semaphores follows:

.. code-block:: yaml

   - semaphore:
       name: semaphore-foo
       max: 5
   - semaphore:
       name: semaphore-bar
       max: 3

See :doc:`semaphore_def` for more information.

.. _pragma:

Pragma
~~~~~~

The `pragma` item does not behave like the others.  It can not be
included or excluded from configuration loading by the administrator,
and does not form part of the final configuration itself.  It is used
to alter how the configuration is processed while loading.

A pragma item only affects the current file.  The same file in another
branch of the same project will not be affected, nor any other files
or any other projects.  The effect is global within that file --
pragma directives may not be set and then unset within the same file.

.. code-block:: yaml

   - pragma:
       implied-branch-matchers: False

See :doc:`pragma_def` for more information.
