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


Advantages
----------

* A more intuitive way to define relevant files for a job using simple set
  operations.
* Saving resources by avoiding to run jobs unnecessarily.
* Combining **includes** and **excludes** in a single attribute avoids
  overriding only one of them in child jobs which could cause confusion.

The proposed name **fileset** is chosen for following reasons:

* It is consistent with existing attribute :attr:`job.nodeset`.
* It indicates the similar logic of `Ant FileSet`_.


Differences to original implementation
--------------------------------------

With the **fileset** matching logic it is not possible to use the "skip if all
files match any" logic anymore. Instead the **excludes** have a "skip if all
**included** files match any" logic. This can cause jobs to be skipped when
before they would have been run.

For this reason some care must be taken when migrating existing jobs to the new
**fileset** configuration by matching all relevant files in the **includes**
and using **excludes** only to further refine the **includes** section.
Typically the **includes** would match common top-level files and directories
which may for example include one software module inside the repository. Then
**excludes** are used to avoid running a job for modifications in certain types
of files within that module like for example documentation files that are
scattered throughout the source tree.

If **includes** matches all files or is omitted and **excludes** is given then
all files are applicable to the **excludes** matching. Therefore the original
"skip if all files match any" logic is still applicable in this special case.


Examples: Old vs. new syntax
----------------------------

.. list-table::
   :width: 100%
   :widths: 25 25 50
   :header-rows: 1

   * - Old syntax
     - New syntax
     - Explanation


   * - .. code-block:: yaml

          - job:
            name: Job_A

            files:
              - A/.*

     - .. code-block:: yaml

          - job:
            name: Job_A
            fileset:
              includes:
                - A/.*

     - | Only the **files** section is specified. The **fileset**
       | **includes** section behaves exactly the same.


   * - .. code-block:: yaml

          - job:
            name: Job_A

            irrelevant-files:
              - .*\.py$


     - .. code-block:: yaml

          - job:
            name: Job_A
            fileset:
              excludes:
                - .*\.py$

     - | Only the **irrelevant-files** section is specified. The
       | **fileset** **excludes** section behaves exactly the
       | same.


   * - .. code-block:: yaml

          - job:
            name: Job_A

            files:
              - A/.*
            irrelevant-files:
              - .*\.py$

     - .. code-block:: yaml

          - job:
            name: Job_A
            fileset:
              includes:
                - A/.*
              excludes:
                - .*\.py$

     - | Both **files** and **irrelevant-files** are specified. When
       | changed to **fileset** **includes** and **excludes**
       | respectively, the behavior is changed in that the
       | **excludes** will only be applied to the files matched
       | by the **includes**, not to all files.


Implementation notes
--------------------

* The existing file matchers match always for changes without files. This
  behavior is preserved also in **fileset**.
* The introduction of **re2** regex module instead of the standard re module is
  currently disscussed. **re2** has limitations related to lookahead
  assertions. The currently used `BfRe2`_ module cannot accept unsupprted
  regular expressions and raises an exception if encountered. However there are
  other python modules which provide an automatic fallback mechanism with the
  intention to provide a drop-in replacement for the standard re module. I
  evaluated `Re2`_ first but it seems it cannot be built in the latest version
  and is probably not maintained actively anymore. Luckily `PyRe2`_ looks more
  promising. I replaced `BfRe2`_ by `PyRe2`_ in Zuul's requirements.txt and
  also added some test using a negative lookahead with the fallback mechanism
  configured. The tests passed and the automatic fallback worked as expected.
  For example a warning like this would be printed:

  .. code-block::

     UserWarning: WARNING: Using re module. Reason: invalid perl operator: (?!

  There are different potential alternatives to
  proceed with this topic:

  #. Keep using standard re module for fileset. Users would not have to care
     about their used regexes and could more directly migrate to fileset.
  #. Use `PyRe2`_ for fileset and add a fallback notification in the form of a
     warning in Zuul log. Ask users to check their used regexes for the file
     filter to ensure they are still working as expected. Regexes with negative
     lookahead may have to be re-formulated using **fileset** **excludes**.
     This could also lead to a more readable configuration as negative
     lookaheads can be a bit confusing.
  #. Use `PyRe2`_ for fileset and also other regexes used in Zuul layout like
     :attr:`job.branches`, etc. Since the include / exclude filter could
     provide a general alternative to negative lookaheads it may be beneficial
     to use it for all such matchers. Also this would provide a more consistent
     solution for matchers and would allow to remove more of the original
     matcher code. In this case we may consider to use also consistent names
     like "branchset", etc. Alternatively we could keep the current names
     :attr:`job.files` and :attr:`job.branches` but allow usage of either
     **includes** and **excludes** as sub-elements or the original regex /
     regex-list and only deprecate :attr:`job.irrelevant-files` and the
     original regex / regex-list usage. An advantage of this general approach
     could be that users would only have to check and migrate their matcher
     configurations and regular expressions once.

.. _BfRe2: https://github.com/facebook/pyre2
.. _Re2: https://github.com/axiak/pyre2/
.. _PyRe2: https://github.com/andreasvc/pyre2


Deprecation and migration plan
------------------------------

Job attributes :attr:`job.files` and :attr:`job.irrelevant-files` will be
deprecated in favor of the new **fileset** attribute. A conversion script will
be provided to ease the migration of existing job configs to **fileset**. In
order to give users enough time to update their configs a reasonable migration
plan needs to be defined:

#. **fileset** feature is merged on Zuul master and old attributes are marked
   as deprecated. The documentation is updated with migration information and a
   migration script is provided. Release notes are extended with the new
   feature and deprecation notice. Notifications about the deprecation and need
   for migration are sent out. This could be within May 2022 timeframe.
#. **fileset** feature is released within the next major Zuul release which
   could be version **7.0.0**.
#. The removal of old attributes and related code is prepared including adding
   a release note entry for the removal. The review process for this change is
   completed but the change is not merged yet. A notification about the removal
   of old attributes is sent out including the target release which could be
   version **8.0.0**.
#. Another notification is sent informing about the removal referencing the
   Gerrit change and target release. The removal of old attributes is merged on
   master shortly before the **8.0.0** release.
#. The **8.0.0** release is done including the removed attributes which
   completes the deprecation and migration plan.
