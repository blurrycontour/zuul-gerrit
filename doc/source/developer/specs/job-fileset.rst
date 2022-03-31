Job Filesets
============

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul. They may change significantly
   before final implementation, or may never be fully completed.

Motivation
----------

Given a project repository with folders A and B and corresponding job:

.. code-block:: yaml

   - job:
      name: Job_A
      files:
      - A/.*
      irrelevant-files:
      - .*\.py$

Job_A generally runs for changes in folder A unless only .py files are changed.
Given the following set of modified files:

* A/a.py
* B/b.cpp

The intuition may be that Job_A is not executed because no relevant files are
modified. But surprisingly Job_A is executed. This behavior is explained by the
matching logic of the files and irrelevant-files matcher and the fact that it
is evaluated based on all modified files instead of only the job's files. To
better understand let's look at what happens in the Job.changeMatchesFiles
method:

.. code-block:: python

   if self.file_matcher and not self.file_matcher.matches(change):
      return False # file_matcher matches irrelevant file A/a.py so
                   # the job is not skipped here.
   if (self.irrelevant_file_matcher and
         self.irrelevant_file_matcher.matches(change)):
      return False # irrelevant_file_macher doesn't match B/b.cpp so
                   # the job is also not skipped here.
   return True # As a result the job is run.

Also see the difference in behavior in following tests provided in the
`implementation proposal`_:

* test_irrelevant_files_one_not_included_one_excluded_runs_job
* test_fileset_one_not_included_one_excluded_skips_job

.. _implementation proposal: https://review.opendev.org/c/zuul/zuul/+/828125/


Proposed change
---------------

Provide an alternative way to define relevant files for a job inspired by `Ant
FileSet`_.

.. _Ant FileSet: https://ant.apache.org/manual-1.9.x/Types/fileset.html

For each job a **fileset** can be configured by defining included and excluded
files (each can be a single regex or a list of regexes), for example:

.. code-block:: yaml

   - job:
      name: Job_A
      fileset:
         includes:
         - A/.*
         excludes:
         - .*\.py$

If no **fileset** is present then the job is run for all changes. A **fileset**
must contain either **includes** or **excludes** or both but cannot be empty.

Omitting **includes** is equivalent to matching all files:

.. code-block:: yaml

   includes: '.*'

Ommitting **excludes** is equivalent to an empty **excludes** (to be exact the
COMMIT_MSG file is always excluded):

.. code-block:: yaml

   excludes: []

To decide whether a job must be executed for a particular change the
**fileset** filter is applied to each modified file of the change separately.
If a file is included and not excluded then it is added to the job's
**fileset**. The job is only executed if its final **fileset** is not empty.

In other words: We define the set of included files by matching the modified
files against the **includes** regexes. Then we can exclude files from the set
of included files by matching them against the **excludes** regexes. The
resulting set of modified files is the set of relevant files for the job. If
it is empty then the job is not run.

Explained in set arithmetic, given:

* **I** the set of modified files matched by **includes**
* **E** the set of modified files matched by **excludes**

Then the set of relevant files for the job is:

**I - E**

Handling of the commit message (COMMIG_MSG file):

Instead of just excluding commit message modifications in general or
hard-coding some rules it would be more flexible to allow the user to decide.
By providing a fileset flag "fileset.include-commit-message" (default is false)
we could allow jobs to be triggered by commit message modifications if needed.
This could be useful for jobs that enforce a commit message guideline or use
certain keywords in the commit message to trigger some action.

Advantages:

* A more intuitive way to define relevant files for a job using simple set
  operations.
* Saving resources by avoiding to run jobs unnecessarily.
* Combining **includes** and **excludes** in a single attribute avoids
  overriding only one of them in child jobs which could cause confusion.

The proposed name **fileset** is chosen for following reasons:

* It is consistent with existing attribute :attr:`job.nodeset`.
* It indicates the similar logic of `Ant FileSet`_.


Deprecation and migration plan
------------------------------

Job attributes :attr:`job.files` and :attr:`job.irrelevant-files` will be
deprecated in favor of the new **fileset** attribute. A conversion script will be
provided to ease the migration of existing job configs to **fileset**. In order to
give users enough time to update their configs a reasonable transition period
of at least 3 months should be defined where both configurations would be
possible. After the transition period the deprecated attributes will be
removed. TBD: Need some guidance from core mainainers to define a proper plan.
