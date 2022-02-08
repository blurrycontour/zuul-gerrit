Data Model Changelog
====================

Record changes to the ZooKeeper data model which require API version
increases here.

When making a model change:

* Increment the value of ``MODEL_API`` in ``model.py``.
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
:Description: Add `SupercedeEvent` and use them for dequeuing of superceded
              items from other pipelines.
