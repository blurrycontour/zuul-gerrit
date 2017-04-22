========================
stdlib.prepare-workspace
========================

Ansible role to prepare a zuul worker to run jobs

* License: Apache License, Version 2.0
* Documentation: TBD
* Source: https://git.openstack.org/cgit/openstack-infra/zuul
* Bugs: TBD

Description
-----------

This role will do the following:

  * Ensure zuul worker console stream is running.
  * Create workspace directory for jobs to run from.
  * Synchronize the required git repositories needs for the job.

Requirements
------------

Role Variables
--------------

Dependencies
------------

There are no role dependencies.

Example Playbook
----------------

.. code-block:: yaml

    - name: Zuul worker
      hosts: all
      roles:
        - stdlib.prepare-workspace
