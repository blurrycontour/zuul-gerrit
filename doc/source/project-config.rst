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
defined in a *config-project* are run with elevated privileges, and
all Zuul configuration items are available for use.  It is expected
that changes to *config-projects* will undergo careful scrutiny before
being merged.

An *untrusted-project* is a project whose primary focus is not to
operate Zuul, but rather it is one of the projects being tested or
deployed.  The Zuul configuration language available to these projects
is somewhat restricted (as detailed in individual section below), and
jobs defined in these projects run in a restricted execution
environment since they may be operating on changes which have not yet
undergone review.

Configuration Loading
---------------------

When Zuul starts, it examines all of the git repositories which are
specified by the system administrator in `admin-config`_ and searches
for files in the root of each repository.  In the case of a
*config-project*, Zuul looks for a file named `zuul.yaml`.  In the
case of an *untrusted-project*, Zuul looks first for `zuul.yaml` and
if that is not found, `.zuul.yaml` (with a leading dot).  In the case
of an *untrusted-project*, the configuration from every branch is
included, however, in the case of a *config-project*, only the
`master` branch is examined.

When a change is proposed to one of these files in an
*untrusted-project*, the configuration proposed in the change is
merged into the running configuration so that any changes to Zuul's
configuration are self-testing as part of that change.  If there is a
configuration error, no jobs will be run and the error will be
reported by any applicable pipelines.  In the case of a change to a
*config-project*, the new configuration is parsed and examined for
errors, but the new configuration is not used in testing the change.
This is because configuration in *config-projects* is able to access
elevated privileges and should always be reviewed before being merged.

As soon as a change containing a Zuul configuration change merges to
any Zuul-managed repository, the new configuration takes effect
immediately.

Configuration Items
-------------------

The `zuul.yaml` and `.zuul.yaml` configuration files are
YAML-formatted and are structured as a series of items, each of which
is described below.

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
project gating.  To do so, one can create a *gate* pipeline which
tells Zuul that when a certain event (such as approval by a code
reviewer) occurs, the corresponding change or pull request should be
enqueued into the pipeline.  When that happens, the jobs which have
been configured to run for that project in the *gate* pipeline are
run, and when they complete, the pipeline reports the results to the
user.

Pipeline configuration items may only appear in *config-projects*.

Generally, a Zuul administrator would define a small number of
pipelines which represent the workflow processes used in their
environment.  Each project can then be added to the available
pipelines as appropriate.

Here is an example *check* pipeline, which runs whenever a new
patchset is created in Gerrit.  If the associated jobs all report
success, the pipeline reports back to Gerrit with a *Verified* vote of
+1, or if at least one of them fails, a -1.

  - pipeline:
    name: check
      manager: independent
      trigger:
        my_gerrit:
          - event: patchset-created
      success:
        my_gerrit:
          verified: 1
      failure:
        my_gerrit
          verified: -1

See TODO for more annotated examples of common pipeline configurations.

The attributes available on a pipeline are as follows (all are
optional unless otherwise specified)::

**name** (required)
  This is used later in the project definition to indicate what jobs
  should be run for events in the pipeline.

**manager** (required)
  There are currently two schemes for managing pipelines:

  *independent*
    Every event in this pipeline should be treated as independent of
    other events in the pipeline.  This is appropriate when the order of
    events in the pipeline doesn't matter because the results of the
    actions this pipeline performs can not affect other events in the
    pipeline.  For example, when a change is first uploaded for review,
    you may want to run tests on that change to provide early feedback
    to reviewers.  At the end of the tests, the change is not going to
    be merged, so it is safe to run these tests in parallel without
    regard to any other changes in the pipeline.  They are independent.

    Another type of pipeline that is independent is a post-merge
    pipeline. In that case, the changes have already merged, so the
    results can not affect any other events in the pipeline.

  *dependent*
    The dependent pipeline manager is designed for gating.  It ensures
    that every change is tested exactly as it is going to be merged
    into the repository.  An ideal gating system would test one change
    at a time, applied to the tip of the repository, and only if that
    change passed tests would it be merged.  Then the next change in
    line would be tested the same way.  In order to achieve parallel
    testing of changes, the dependent pipeline manager performs
    speculative execution on changes.  It orders changes based on
    their entry into the pipeline.  It begins testing all changes in
    parallel, assuming that each change ahead in the pipeline will pass
    its tests.  If they all succeed, all the changes can be tested and
    merged in parallel.  If a change near the front of the pipeline
    fails its tests, each change behind it ignores whatever tests have
    been completed and are tested again without the change in front.
    This way gate tests may run in parallel but still be tested
    correctly, exactly as they will appear in the repository when
    merged.

    For more detail on the theory and operation of Zuul's dependent
    pipeline manager, see: :doc:`gating`.

**description**
  This field may be used to provide a textual description of the
  pipeline.

**success-message**
  The introductory text in reports when all the voting jobs are
  successful.  Defaults to "Build successful."

**failure-message**
  The introductory text in reports when at least one voting job fails.
  Defaults to "Build failed."

**merge-failure-message**
  The introductory text in message reported back to Gerrit when a
  change fails to merge with the current state of the repository.
  Defaults to "Merge failed."

**footer-message**
  Supplies additional information after test results.  Useful for
  adding information about the CI system such as debugging and contact
  details.

**trigger**
  At least one trigger source must be supplied for each pipeline.
  Triggers are not exclusive -- matching events may be placed in
  multiple pipelines, and they will behave independently in each of
  the pipelines they match.

  Triggers are loaded from their connection name. The driver type of
  the connection will dictate which options are available.
  See :doc:`triggers`.

**require**
  If this section is present, it established pre-requisites for any
  kind of item entering the Pipeline.  Regardless of how the item is
  to be enqueued (via any trigger or automatic dependency resolution),
  the conditions specified here must be met or the item will not be
  enqueued.

.. TODO this section is in flux in v3 _pipeline-require-approval:

  **approval**
  This requires that a certain kind of approval be present for the
  current patchset of the change (the approval could be added by the
  event in question).  It takes several sub-parameters, all of which
  are optional and are combined together so that there must be an
  approval matching all specified requirements.

    *username*
    If present, an approval from this username is required.  It is
    treated as a regular expression.

    *email*
    If present, an approval with this email address is required.  It
    is treated as a regular expression.

    *email-filter* (deprecated)
    A deprecated alternate spelling of *email*.  Only one of *email* or
    *email_filter* should be used.

    *older-than*
    If present, the approval must be older than this amount of time
    to match.  Provide a time interval as a number with a suffix of
    "w" (weeks), "d" (days), "h" (hours), "m" (minutes), "s"
    (seconds).  Example ``48h`` or ``2d``.

    *newer-than*
    If present, the approval must be newer than this amount of time
    to match.  Same format as "older-than".

    Any other field is interpreted as a review category and value
    pair.  For example ``verified: 1`` would require that the approval
    be for a +1 vote in the "Verified" column.  The value may either
    be a single value or a list: ``verified: [1, 2]`` would match
    either a +1 or +2 vote.

  **open**
  A boolean value (``true`` or ``false``) that indicates whether the change
  must be open or closed in order to be enqueued.

  **current-patchset**
  A boolean value (``true`` or ``false``) that indicates whether the change
  must be the current patchset in order to be enqueued.

  **status**
  A string value that corresponds with the status of the change
  reported by the trigger.
   
**reject**
  If this section is present, it establishes pre-requisites that can
  block an item from being enqueued. It can be considered a negative
  version of **require**.

  **approval**
  This takes a list of approvals. If an approval matches the provided
  criteria the change can not be entered into the pipeline. It follows
  the same syntax as the :ref:`"require approval" pipeline above
  <pipeline-require-approval>`.

  Example to reject a change with any negative vote::

    reject:
      approval:
        - code-review: [-1, -2]

**dequeue-on-new-patchset**
  Normally, if a new patchset is uploaded to a change that is in a
  pipeline, the existing entry in the pipeline will be removed (with
  jobs canceled and any dependent changes that can no longer merge as
  well.  To suppress this behavior (and allow jobs to continue
  running), set this to ``false``.  Default: ``true``.

**ignore-dependencies**
  In any kind of pipeline (dependent or independent), Zuul will
  attempt to enqueue all dependencies ahead of the current change so
  that they are tested together (independent pipelines report the
  results of each change regardless of the results of changes ahead).
  To ignore dependencies completely in an independent pipeline, set
  this to ``true``.  This option is ignored by dependent pipelines.
  The default is: ``false``.

The following options configure *reporters*.  Reporters are
complementary to triggers; where a trigger is an event on a connection
which causes Zuul to enqueue an item, a reporter is the action
performed on a connection when an item is dequeued after its jobs
complete.  The actual syntax for a reporter is defined by the driver
which implements it.  See :ref:`drivers` for more information.
  
**success**
  Describes where Zuul should report to if all the jobs complete
  successfully.  This section is optional; if it is omitted, Zuul will
  run jobs and do nothing on success -- it will not report at all.  If
  the section is present, the listed reporters will be asked to report
  on the jobs.  The reporters are listed by their connection name. The
  options available depend on the driver for the supplied connection.

**failure**
  These reporters describe what Zuul should do if at least one job
  fails.

**merge-failure**
  These reporters describe what Zuul should do if it is unable to
  merge in the patchset. If no merge-failure reporters are listed then
  the ``failure`` reporters will be used to notify of unsuccessful
  merges.

**start**
  These reporters describe what Zuul should do when a change is added
  to the pipeline.  This can be used, for example, to reset a
  previously reported result.

**disabled**
  These reporters describe what Zuul should do when a pipeline is
  disabled.  See ``disable-after-consecutive-failures``.

**disable-after-consecutive-failures**
  If set, a pipeline can enter a ''disabled'' state if too many changes
  in a row fail. When this value is exceeded the pipeline will stop
  reporting to any of the ``success``, ``failure`` or ``merge-failure``
  reporters and instead only report to the ``disabled`` reporters.
  (No ``start`` reports are made when a pipeline is disabled).

**precedence**
  Indicates how the build scheduler should prioritize jobs for
  different pipelines.  Each pipeline may have one precedence, jobs
  for pipelines with a higher precedence will be run before ones with
  lower.  The value should be one of ``high``, ``normal``, or ``low``.
  Default: ``normal``.

**window**
  Dependent pipeline managers only. Zuul can rate limit dependent
  pipelines in a manner similar to TCP flow control.  Jobs are only
  started for items in the queue if they are within the actionable
  window for the pipeline. The initial length of this window is
  configurable with this value. The value given should be a positive
  integer value. A value of ``0`` disables rate limiting on the
  DependentPipelineManager.  Default: ``20``.

**window-floor**
  Dependent pipeline managers only. This is the minimum value for the
  window described above. Should be a positive non zero integer value.
  Default: ``3``.

**window-increase-type**
  Dependent pipeline managers only. This value describes how the window
  should grow when changes are successfully merged by zuul. A value of
  ``linear`` indicates that ``window-increase-factor`` should be added
  to the previous window value. A value of ``exponential`` indicates
  that ``window-increase-factor`` should be multiplied against the
  previous window value and the result will become the window size.
  Default: ``linear``.

**window-increase-factor**
  Dependent pipeline managers only. The value to be added or multiplied
  against the previous window value to determine the new window after
  successful change merges.
  Default: ``1``.

**window-decrease-type**
  Dependent pipeline managers only. This value describes how the window
  should shrink when changes are not able to be merged by Zuul. A value
  of ``linear`` indicates that ``window-decrease-factor`` should be
  subtracted from the previous window value. A value of ``exponential``
  indicates that ``window-decrease-factor`` should be divided against
  the previous window value and the result will become the window size.
  Default: ``exponential``.

**window-decrease-factor**
  Dependent pipline managers only. The value to be subtracted or divided
  against the previous window value to determine the new window after
  unsuccessful change merges.
  Default: ``2``.


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
as `final`, some attributes may not be overidden).

Jobs also support a concept called variance.  The first time a job
definition appears is called the reference definition of the job.
Subsequent job definitions with the same name are called variants.
These may have different selection criteria which indicate to Zuul
that, for instance, the job should behave differently on a different
git branch.  Unlike inheritance, all job variants must be defined in
the same project.

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

* parent pre-playbook
* child pre-playbook
* child playbook
* child post-playbook
* parent post-playbook

Further inheritance would nest even deeper.

Here is an example of two job definitions::

  - job:
      name: base
      pre-run: copy-git-repos
      post-run: copy-logs

  - job:
      name: run-tests
      parent: base
      nodes:
        - name: test-node
	  image: fedora

The following attributes are available on a job; all are optional
unless otherwise specified:

**name** (required)
  The name of the job.  By default, Zuul looks for a playbook with
  this name to use as the main playbook for the job.  This name is
  also referenced later in a project pipeline configuration.

**parent**
  Specifies a job to inherit from.  The parent job can be defined in
  this or any other project.  Any attributes not specified on a job
  will be collected from its parent.

**success-message**
  Normally when a job succeeds, the string "SUCCESS" is reported as
  the result for the job.  If set, this option may be used to supply a
  different string.  Default: "SUCCESS".

**failure-message**
  Normally when a job fails, the string "FAILURE" is reported as
  the result for the job.  If set, this option may be used to supply a
  different string.  Default: "FAILURE".

**success-url**
  When a job succeeds, this URL is reported along with the result.
  Default: none.

**failure-url**
  When a job fails, this URL is reported along with the result.
  Default: none.

**hold-following-changes**
  In a dependent pipeline, this option may be used to indicate that no
  jobs should start on any items which depend on the current item
  until this job has completed successfully.  This may be used to
  conserve build resources, at the expense of inhibiting the
  parallelization which speeds the processing of items in a dependent
  pipeline.  A boolean value, default: false.

**voting**
  Indicates whether the result of this job should be used in
  determining the overall result of the item.  A boolean value,
  default: true.

**semaphore**
  The name of a :ref:`semaphore` which should be acquired and released
  when the job begins and ends.  If the semaphore is at maximum
  capacity, then Zuul will wait until it can be acquired before
  starting the job.  Default: none.

**tags**
  Metadata about this job.  Tags are units of information attached to
  the job; they do not affect Zuul's behavior, but they can be used
  within the job to characterize the job.  For example, a job which
  tests a certain subsystem could be tagged with the name of that
  subsystem, and if the job's results are reported into a database,
  then the results of all jobs affecting that subsystem could be
  queried.  This attribute is specified as a list of strings, and when
  inheriting jobs or applying variants, tags accumulate in a set, so
  the result is always a set of all the tags from all the jobs and
  variants used in constructing the frozen job, with no duplication.
  Default: none.

** branches **
  A regular expression (or list of regular expressions) which describe
  on what branches a job should run (or in the case of variants: to
  alter the behavior of a job for a certain branch).

  If there is no job definition for a given job which matches the
  branch of an item, then that job is not run for the item.
  Otherwise, all of the job variants which match that branch (and any
  other selection criteria) are used when freezing the job.

  This example illustrates a job called *run-tests* which uses a
  nodeset based on the current release of an operating system to
  perform its tests, except when testing changes to the stable/2.0
  branch, in which case it uses an older release::

    - job:
        name: run-tests
	nodes: current-release
      
    - job:
        name: run-tests
	branch: stable/2.0
	nodes: old-release

  In some cases, Zuul uses an implied value for the branch specifier
  if none is supplied:

  * For a job definition in a *config-project*, no implied branch
    specifier is used.  If no branch specifier appears, the job
    applies to all branches.

  * In the case of an *untrusted-project*, no implied branch specifier
    is applied to the reference definition of a job.  That is to say,
    that if the first appearance of the job definition appears without
    a branch specifier, then it will apply to all branches.  Note that
    when collecting its configuration, Zuul reads the `master` branch
    of a given project first, then other branches in alphabetical
    order.

  * Any further job variants other than the reference definition in an
    *untrusted-project* will, if they do not have a branch specifier,
    will have an implied branch specifier for the current branch
    applied.
  
  This allows for the very simple and expected workflow where if a
  project defines a job on the master branch with no branch specifier,
  and then creates a new branch based on master, any changes to that
  job definition within the new branch only affect that branch.
    
**files**
  This attribute indicates that the job should only run on changes
  where the specified files are modified.  This is a regular
  expression or list of regular expressions.  Default: none.

**irrelevant-files**
  This is a negative complement of `files`.  It indicates that the job
  should run unless *all* of the files changed match this list.  In
  other words, if the regular expression `docs/.*` is supplied, then
  this job will not run if the only files changed are in the docs
  directory.  A regular expression or list of regular expressions.
  Default: none.

**auth**
  Authentication information to be made available to the job.

               'auth': auth,
               'nodes': vs.Any([node], str),
               'timeout': int,
               'attempts': int,
               'pre-run': to_list(str),
               'post-run': to_list(str),
               'run': str,
               '_source_context': model.SourceContext,
               '_start_mark': yaml.Mark,
               'roles': to_list(role),
               'repos': to_list(str),
               'vars': dict,
               'dependencies': to_list(str),
               'allowed-projects': to_list(str),


.. _project:

Project
~~~~~~~

.. _project-template:

Project Template
~~~~~~~~~~~~~~~~

.. _secret:

Secret
~~~~~~

.. _nodeset:

Nodeset
~~~~~~~

.. _semaphore:

Semaphore
~~~~~~~~~
