:title: Zuul Admin Client

Zuul Admin Client
=================

Zuul includes a simple command line client that may be used to affect Zuul's
behavior while running.

.. note:: For operations related to normal workflow like enqueue, dequeue, autohold and promote, the `zuul-client` CLI should be used instead.

Configuration
-------------

The client uses the same zuul.conf file as the server, and will look
for it in the same locations if not specified on the command line.

Usage
-----
The general options that apply to all subcommands are:

.. program-output:: zuul-admin --help

The following subcommands are supported:

tenant-conf-check
^^^^^^^^^^^^^^^^^

.. program-output:: zuul-admin tenant-conf-check --help

Example::

  zuul-admin tenant-conf-check

This command validates the tenant configuration schema. It exits '-1' in
case of errors detected.

create-auth-token
^^^^^^^^^^^^^^^^^

.. note:: This command is only available if an authenticator is configured in
          ``zuul.conf``. Furthermore the authenticator's configuration must
          include a signing secret.

.. program-output:: zuul-admin create-auth-token --help

Example::

    zuul-admin create-auth-token --auth-config zuul-operator --user alice --tenant tenantA --expires-in 1800

The return value is the value of the ``Authorization`` header the user must set
when querying a protected endpoint on Zuul's REST API.

Example::

    bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwOi8vbWFuYWdlc2Yuc2ZyZG90ZXN0aW5zdGFuY2Uub3JnIiwienV1bC50ZW5hbnRzIjp7ImxvY2FsIjoiKiJ9LCJleHAiOjE1Mzc0MTcxOTguMzc3NTQ0fQ.DLbKx1J84wV4Vm7sv3zw9Bw9-WuIka7WkPQxGDAHz7s

export-keys
^^^^^^^^^^^

.. program-output:: zuul-admin export-keys --help

Example::

  zuul-admin export-keys /var/backup/zuul-keys.json

import-keys
^^^^^^^^^^^

.. program-output:: zuul-admin import-keys --help

Example::

  zuul-admin import-keys /var/backup/zuul-keys.json

copy-keys
^^^^^^^^^

.. program-output:: zuul-admin copy-keys --help

Example::

  zuul-admin copy-keys gerrit old_project gerrit new_project

delete-keys
^^^^^^^^^^^

.. program-output:: zuul-admin delete-keys --help

Example::

  zuul-admin delete-keys gerrit old_project

delete-state
^^^^^^^^^^^^

.. program-output:: zuul-admin delete-state --help

Example::

  zuul-admin delete-state

delete-pipeline-state
^^^^^^^^^^^^^^^^^^^^^

.. program-output:: zuul-admin delete-pipeline-state --help

Example::

  zuul-admin delete-pipeline-state tenant pipeline
