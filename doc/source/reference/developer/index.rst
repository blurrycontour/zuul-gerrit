Developer's Guide
=================

This section contains information for Developers who wish to work on
Zuul itself.  This information is not necessary for the operation of
Zuul, though advanced users may find it interesting.

Our project makes use of tox_ for running most of the python tests
and yarn_ for the the `web/` bits.

To see a list of all available commands run the commands below.

.. command-output:: tox -va

.. command-output:: yarn --non-interactive --cwd=web run

.. autoclass:: zuul.scheduler.Scheduler

.. toctree::
   :maxdepth: 1

   datamodel
   drivers
   triggers
   testing
   docs
   ansible
   javascript
   specs/index
   releasenotes

.. _tox: https://tox.readthedocs.io/en/latest/config.html
.. _yarn: https://classic.yarnpkg.com/en/
