Superproject subscription to submodules updates
===============================================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

Gerrit has support for `superproject subscription to submodule updates`_.

  When a superproject is subscribed to a submodule, it is not required
  to push/merge commits to this superproject to update the gitlink to
  the submodule. Whenever a commit is merged in a submodule, its
  subscribed superproject is updated by Gerrit.

  -- Gerrit Code Review

.. _superproject subscription to submodule updates: https://gerrit-review.googlesource.com/Documentation/user-submodules.html

Zuul is currently unaware of this, which means that the speculative
merge does not take the information into account. This design aims to
teach Zuul about automatic updated of version information, not just
in Git submodules.

When Zuul knows about updated version information, it seems unfortunate
that it will only work together with submodule updates in Gerrit.
Therefore, it is suggested that a Zuul push the resulting merges so
that automatic version updates work independent of Git server setup.

Proposed Change
---------------

Project Configuration
~~~~~~~~~~~~~~~~~~~~~

We suggest a new field in the project configuration:

.. code-block:: yaml

  project-subscriptions:
    - name: "(Canonical) name of the submodule project"
      branch: "'.' or another branch name"

`branch = .` means that the a super project is tracking the same branch
name in the submodule. Using `branch = .` should be considered as the
default case, but in some cases, tracking a `stable` or release branch
might make sense.

Trigger Super Project Jobs
~~~~~~~~~~~~~~~~~~~~~~~~~~

We should create a new change type `GeneratedChange` with the subclass
`ProjectSubscriptionChange`. When a `QueueItem` gets inserted into a
pipeline, the project configurations might generate new changes for
other (super) projects and insert them into the (circular dependency)
cycle of the `QueueItem`. Note that the items ahead in the queue may
well affect which changes get generated, so when a `QueueItem` is moved
around, the set of generated changes need to be reset.

Generating new changes makes the job resolution of logic run for the
super projects, so that they are verified as well. We don't want any
broken update in the super project to pass gate. The generated change
also gives a natural way for processing the updates by the reporters.

Note that this design allows for recursive project subscriptions,
between and project and branch combination.

Updating Project Content
~~~~~~~~~~~~~~~~~~~~~~~~

Given a set of generated changes, the mergers need to update version
information. It can be Git submodule gitlinks, Repo `manifest.xml`
files, `MODULE.bazel` or something else. This requires a plugin system
for merging which depends on the projects themselves. The suggested
design is to extend the project definition with a `merge-job` which can
return the updated repository. The configuration freeze, including
determining the `merge-job` configuration, will still be based on the
built in merge result, but the code that the other jobs will check out
will depend on the `merge-job` configuration.

Note that the merge job is not limited to just update version
information, it can potentially also apply automatic lint fixes. Such
fixes will though bypass manual review steps.

Push Automatic Updates
~~~~~~~~~~~~~~~~~~~~~~

The only support for automatic submodule update in super projects is
when both the submodule and the super project are located in the same
Gerrit instance. Given the `merge-job`, it makes sense to let Zuul push
the merge result to the Git servers. This would extend the support to
all Git servers and all types of automatic changes.

While adding push support, it makes sense to make the merging process
deterministic so that the pushed commits are the same as the commits
verified in the gate pipeline. Basically, use the `BuildSet` or
`QueueItem` creation time as commit date.

To not interfere with existing reporters, it is suggested that a new
`GitPushReporter` is implemented that will push the changes made by the
merger to any type of Git server. This reporter can then be used in
conjunction with other existing reporters for Gerrit, Gitlab and GitHub
etc.

Implementation wise, phase 1 will push the change upstream to
`refs/zuul/{uuid}` and verify that the remote tip of the branch is at
part of the history. Then phase 2 will push to `refs/heads/{branch}`,
which is just a matter of pointing a ref to a new commit.

Work Items
----------

* Add parsing of `project-subscription` to the project configuration
  parsing.

* Add `ProjectSubscriptionChange` to build sets and to
  `ZooKeeperCache`. Remove these changes from build sets when
  rearranging a `ChangeQueue`.

* Implement `merge-job` configuration and let the result of the
  `merge-job` be used by the other jobs.

* Implement a `GitPushReporter` which can push to any type of Git
  server.

* Make sure submitting can be disabled by configuration in all the
  other reporters.

Considered Alternatives
-----------------------

Reading .gitmodules
~~~~~~~~~~~~~~~~~~~

Reading `.gitmodules` to acquire project subscription information is
technically possible, but that is only one out of many ways to describe
dependencies. Therefore, the suggestion is to run a job that verifies
that the checked in Zuul project configuration matches the
`.gitmodules` file or other sources.

Let Untrusted Projects Add Jobs To Other Projects
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Instead of a new `project-subscription` section in the project
configuration, special untrusted projects could get the possibility
to add jobs to other projects. This way, a super project can add
its own jobs to all the submodules.

The following example is based on `superproject-example`_.

.. _superproject-example: https://github.com/superproject-example/

.. code-block:: yaml

  # super-project/zuul.yaml
  - job:
    name: superproject-specific-job
    description: |
      This job should only run on changes to the superproject.

  - job:
    name: integration-test-job
    description: |
      This job should run on every change to the superproject or any
      submodule project.

  - project-template:
      name: submodule-jobs
      description: |
        A collection of jobs that should run on any change to
        submodules.
      check:
        jobs:
          - integration-test-job

  # Apply the integration tests to the submodules.
  - project:
      name: submodule1
      templates:
      - submodule-jobs

  - project:
      name: submodule2
      templates:
      - submodule-jobs

  # We want to run the superproject job here, and also the
  # integration test job.
  - project:
      templates: submodule-jobs
      check:
        jobs:
          - superproject-specific-job

The downside is that the reporters also need to know about the
subscription. Having job configuration is not enough to indicate to a
reporter that a certain project will be updated.

Even if this suggestion solved the job configuration problem, it does
not provide enough information to the reporters.

Let Zuul Perform Merging internally
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Instead of making the Zuul mergers plugin based, Zuul could be extended
to natively support Git submodules. The problem is all other ways of
expressing version information, so limiting Zuul to only one of those
ways seems unfair and not scalable.

Server Side Merger Script instead of Merge Job
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Instead of using a merge job, the executors could be configured to
execute an installed script. This limits all tenants to use the same
merge script and will also limit the branches to be able to change the
way version information is described.

Because of the flexibility of describing the merge process in a job, a
merge-job seems like the better solution.

External Push Service
~~~~~~~~~~~~~~~~~~~~~

It is possible to use the existing event publishing reporters, for
example the MQTT reporter, and let an external service push the
commits. That will require the external service to make the merge
again and have all repositories checked out. Compared to forking
Zuul and implementing push within the existing drivers, an external
service requires more work to implement and probably gives higher
maintenance burden with integrations instead of simpler unit tests.
Note that such a remote submitting driver must be implemented in a
synchronous manner.
