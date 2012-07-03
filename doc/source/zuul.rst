:title: Zuul

Zuul
====

Configuration
-------------

Zuul has three configuration files:

**zuul.conf**
  Credentials for Gerrit and Jenkins, locations of the other config files
**layout.yaml**
  Project and queue configuration -- what Zuul does
**logging.conf**
    Python logging config

Examples of each of the three files can be found in the etc/ directory
of the source distribution.

zuul.conf
~~~~~~~~~

Zuul will look for ``/etc/zuul/zuul.conf`` or ``~/zuul.conf`` to
bootstrap its configuration.  Alternately, you may specify ``-c
/path/to/zuul.conf`` on the command line.

Gerrit and Jenkins credentials are each described in a section of
zuul.conf.  The location of the other two configuration files (as well
as the location of the PID file when running Zuul as a server) are
specified in a third section.

layout.yaml
~~~~~~~~~~~

This is the main configuration file for Zuul, where all of the queues
and projects are defined, what tests should be run, and what actions
Zuul should perform.  There are three sections: queues, jobs, and
projects.

Queues
""""""

Zuul can have any number of independent queues.  Whenever a matching
Gerrit event is found for a queue, that event is added to the queue,
and the jobs specified for that queue are run.  When all jobs
specified for the queue that were triggered by an event are completed,
Zuul reports back to Gerrit the results.

There are no pre-defined queues in Zuul, rather you can define
whatever queues you need in the layout file.  This is a very flexible
system that can accommodate many kinds of workflows.  

Here is a quick example of a queue definition followed by an
explanation of each of the parameters::

  - name: check
    manager: IndependentQueueManager
    trigger:
      - event: patchset-created
    success:
      verified: 1
    failure:
      verified: -1

**name**
  This is used later in the project definition to indicate what jobs
  should be run for events in the queue.

**manager**
  There are currently two schemes for managing queues:

  *IndependentQueueManager*
    Every event in this queue should be treated as independent of
    other events in the queue.  This is appropriate when the order of
    events in the queue doesn't matter because the results of the
    actions this queue performs can not affect other events in the
    queue.  For example, when a change is first uploaded for review,
    you may want to run tests on that change to provide early feedback
    to reviewers.  At the end of the tests, the change is not going to
    be merged, so it is safe to run these tests in parallel without
    regard to any other changes in the queue.  They are independent.

    Another type of queue that is independent is a post-merge queue.
    In that case, the changes have already merged, so the results can
    not affect any other events in the queue.

  *DependentQueueManager*
    The dependent queue manager is designed for gating.  It ensures
    that every change is tested exactly as it is going to be merged
    into the repository.  An ideal gating system would test one change
    at a time, applied to the tip of the repository, and only if that
    change passed tests would it be merged.  Then the next change in
    line would be tested the same way.  In order to achieve parallel
    testing of changes, the dependent queue manager performs
    speculative execution on changes.  It orders changes based on
    their entry into the queue.  It begins testing all changes in
    parallel, assuming that each change ahead in the queue will pass
    its tests.  If they all succeed, all the changes can be tested and
    merged in parallel.  If a change near the front of the queue fails
    its tests, each change behind it ignores whatever tests have been
    completed and are tested again without the change in front.  This
    way gate tests may run in parallel but still be tested correctly,
    exactly as they will appear in the repository when merged.

    One important characteristic of the DependentQueueManager is that
    it analyzes the jobs that are triggered by different projects, and
    if those projects have jobs in common, it treats those projects as
    related, and they share a single virtual queue of changes.  Thus,
    if there is a job that performs integration testing on two
    projects, those two projects will automatically share a virtual
    change queue.  If a third project does not invoke that job, it
    will be part of a separate virtual change queue, and changes to it
    will not depend on changes to the first two jobs.

    For more detail on the theory and operation of Zuul's
    DependentQueueManager, see: :doc:`gating`.

**trigger**
  This describes what Gerrit events should be placed in the queue.
  Triggers are not exclusive -- matching events may be placed in
  multiple queues, and they will behave independently in each of the
  queues they match.  Multiple triggers may be listed.  Further
  parameters describe the kind of events that match:

  *event*
  The event name from gerrit.  Examples: ``patchset-created``,
  ``comment-added``, ``ref-updated``.  This field is treated as a
  regular expression.

  *branch*
  The branch associated with the event.  Example: ``master``.  This
  field is treated as a regular expression, and multiple branches may
  be listed.

  *ref*
  On ref-updated events, the branch parameter is not used, instead the
  ref is provided.  Currently Gerrit has the somewhat idiosyncratic
  behavior of specifying bare refs for branch names (e.g., ``master``),
  but full ref names for other kinds of refs (e.g., ``refs/tags/foo``).
  Zuul matches what you put here exactly against what Gerrit
  provides.  This field is treated as a regular expression, and
  multiple refs may be listed.

  *approval*
  This is only used for ``comment-added`` events.  It only matches if
  the event has a matching approval associated with it.  Example:
  ``code-review: 2`` matches a ``+2`` vote on the code review category.
  Multiple approvals may be listed.

  *comment_filter*
  This is only used for ``comment-added`` events.  It accepts a list of
  regexes that are searched for in the comment string. If any of these
  regexes matches a portion of the comment string the trigger is
  matched. ``comment_filter: retrigger`` will match when comments
  containing 'retrigger' somewhere in the comment text are added to a
  change.

**success**
  Describes what Zuul should do if all the jobs complete successfully.
  This section is optional; if it is omitted, Zuul will run jobs and
  do nothing on success; it will not even report a message to Gerrit.
  If the section is present, it will leave a message on the Gerrit
  review.  Each additional argument is assumed to be an argument to
  ``gerrit review``, with the boolean value of ``true`` simply
  indicating that the argument should be present without following it
  with a value.  For example, ``verified: 1`` becomes ``gerrit
  review --verified 1`` and ``submit: true`` becomes ``gerrit review
  --submit``.

**failure** 
  Uses the same syntax as **success**, but describes what Zuul should
  do if at least one job fails.

**start** 
  Uses the same syntax as **success**, but describes what Zuul should
  do when a change is added to the queue manager.  This can be used,
  for example, to reset the value of the Verified review category.
  
Some example queue configurations are included in the sample layout
file.  The first is called a *check* queue::

  - name: check
    manager: IndependentQueueManager
    trigger:
      - event: patchset-created
    success:
      verified: 1
    failure:
      verified: -1

This will trigger jobs each time a new patchset (or change) is
uploaded to Gerrit, and report +/-1 values to Gerrit in the
``verified`` review category. ::

  - name: gate
    manager: DependentQueueManager
    trigger:
      - event: comment-added
        approval:
          - approved: 1
    success:
      verified: 2
      submit: true
    failure:
      verified: -2

This will trigger jobs whenever a reviewer leaves a vote of ``1`` in the
``approved`` review category in Gerrit (a non-standard category).
Changes will be tested in such a way as to guarantee that they will be
merged exactly as tested, though that will happen in parallel by
creating a virtual queue of dependent changes and performing
speculative execution of jobs. ::

  - name: post
    manager: IndependentQueueManager
    trigger:
      - event: ref-updated
        ref: ^(?!refs/).*$

This will trigger jobs whenever a change is merged to a named branch
(e.g., ``master``).  No output will be reported to Gerrit.  This is
useful for side effects such as creating per-commit tarballs. ::

  - name: silent
    manager: IndependentQueueManager
    trigger:
      - event: patchset-created

This also triggers jobs when changes are uploaded to Gerrit, but no
results are reported to Gerrit.  This is useful for jobs that are in
development and not yet ready to be presented to developers.

Jobs
""""

The jobs section is optional, and can be used to set attributes of
jobs that are independent of their association with a project.  For
example, if a job should return a customized message on failure, that
may be specified here.  Otherwise, Zuul does not need to be told about
each job as it builds a list from the project specification.

**name**
  The name of the job.  This field is treated as a regular expression
  and will be applied to each job that matches.

**failure-message**
  The message that should be reported to Gerrit if the job fails
  (optional).

**success-message**
  The message that should be reported to Gerrit if the job fails
  (optional).

**branch**
  This job should only be run on matching branches.  This field is
  treated as a regular expression and multiple branches may be
  listed.

Here is an example of setting the failure message for jobs that check
whether a change merges cleanly::

  - name: ^.*-merge$
    failure-message: This change was unable to be automatically merged
    with the current state of the repository. Please rebase your
    change and upload a new patchset.

Projects
""""""""

The projects section indicates what jobs should be run in each queue
for events associated with each project.  It contains a list of
projects.  Here is an example::

  - name: example/project
    check:
      - project-merge:
        - project-unittest
	- project-pep8
	- project-pyflakes
    gate:
      - project-merge:
        - project-unittest
	- project-pep8
	- project-pyflakes
    post:
      - project-publish

**name**
  The name of the project (as known by Gerrit).

This is followed by a section for each of the queues defined above.
Queues may be omitted if no jobs should run for this project in a
given queue.  Within the queue section, the jobs that should be
executed are listed.  If a job is entered as a dictionary key, then
jobs contained within that key are only executed if the key job
succeeds.  In the above example, project-unittest, project-pep8, and
project-pyflakes are only executed if project-merge succeeds.  This
can help avoid running unnecessary jobs.

.. seealso:: The OpenStack Zuul configuration for a comprehensive example: https://github.com/openstack/openstack-ci-puppet/blob/master/modules/openstack-ci-config/files/zuul/layout.yaml


logging.conf
~~~~~~~~~~~~
This file is optional.  If provided, it should be a standard
:mod:`logging.config` module configuration file.  If not present, Zuul will
output all log messages of DEBUG level or higher to the console.

Starting Zuul
-------------

To start Zuul, run **zuul-server**::

  usage: zuul-server [-h] [-c CONFIG] [-d]

  Project gating system.

  optional arguments:
    -h, --help  show this help message and exit
    -c CONFIG   specify the config file
    -d          do not run as a daemon

You may want to use the ``-d`` argument while you are initially setting
up Zuul so you can detect any configuration errors quickly.  Under
normal operation, omit ``-d`` and let Zuul run as a daemon.

If you send signal 1 (SIGHUP) to the zuul-server process, Zuul will
stop executing new jobs, wait until all executing jobs are finished,
reload its configuration, and resume.  Any values in any of the
configuration files may be changed, except the location of Zuul's PID
file (a change to that will be ignored until Zuul is restarted).
