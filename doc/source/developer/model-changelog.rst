Data Model Changelog
====================

Record changes to the ZooKeeper data model which require API version
increases here.

When making a model change:

* Increment the value of ``MODEL_API`` in ``model_api.py``.
* Update code to use the new API by default and add
  backwards-compatibility handling for older versions.  This makes it
  easier to clean up backwards-compatibility handling in the future.
* Make sure code that special cases model versions either references a
  ``model_api`` variable or has a comment like `MODEL_API: >
  {version}` so that we can grep for that and clean up compatability
  code that is no longer needed.
* Add a test to ``test_model_upgrade.py``.
* Add an entry to this log so we can decide when to remove
  backwards-compatibility handlers.

Version 0
---------

:Prior Zuul version: 4.11.0
:Description: This is an implied version as of Zuul 4.12.0 to
              initialize the series.

Version 1
---------

:Prior Zuul version: 4.11.0
:Description: No change since Version 0.  This explicitly records the
              component versions in ZooKeeper.

Version 2
---------

:Prior Zuul version: 5.0.0
:Description: Changes the sempahore handle format from `<item_uuid>-<job_name>`
              to a dictionary with buildset path and job name.

Version 3
---------

:Prior Zuul version: 5.0.0
:Description: Add a new `SupercedeEvent` and use that for dequeuing of
              superceded items from other pipelines. This only affects the
              schedulers.

Version 4
---------

:Prior Zuul version: 5.1.0
:Description: Adds QueueItem.dequeued_missing_requirements and sets it to True
              if a change no longer meets merge requirements in dependent
              pipelines.  This only affects schedulers.

Version 5
---------

:Prior Zuul version: 5.1.0
:Description: Changes the result data attributes on Build from
              ResultData to JobData instances and uses the
              inline/offloading paradigm from FrozenJob.  This affects
              schedulers and executors.

Version 6
---------

:Prior Zuul version: 5.2.0
:Description: Stores the complete layout min_ltimes in /zuul/layout-data.
              This only affects schedulers.

Version 7
---------

:Prior Zuul version: 5.2.2
:Description: Adds the blob store and stores large secrets in it.
              Playbook secret references are now either an integer
              index into the job secret list, or a dict with a blob
              store key.  This affects schedulers and executors.

Version 8
---------

:Prior Zuul version: 6.0.0
:Description: Deduplicates jobs in dependency cycles.  Affects
              schedulers only.

Version 9
---------

:Prior Zuul version: 6.3.0
:Description: Adds nodeset_alternatives and nodeset_index to frozen job.
              Removes nodset from frozen job.  Affects schedulers and executors.

Version 10
----------

:Prior Zuul version: 6.4.0
:Description: Renames admin_rules to authz_rules in unparsed abide.
              Affects schedulers and web.

Version 11
----------

:Prior Zuul version: 8.0.1
:Description: Adds merge_modes to branch cache.  Affects schedulers and web.

Version 12
----------
:Prior Zuul version: 8.0.1
:Description: Adds job_versions and build_versions to BuildSet.
              Affects schedulers.

Version 13
----------
:Prior Zuul version: 8.2.0
:Description: Stores only the necessary event info as part of a queue item
              instead of the full trigger event.
              Affects schedulers.

Version 14
----------
:Prior Zuul version: 8.2.0
:Description: Adds the pre_fail attribute to builds.
              Affects schedulers.
