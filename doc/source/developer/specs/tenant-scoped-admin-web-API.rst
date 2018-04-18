===========================
Tenant-scoped admin web API
===========================

https://storyboard.openstack.org/#!/story/2001771

The aim of this spec is to extend the existing web API of Zuul to
privileged actions, and to scope these actions to tenants and privileged users.

Problem Description
===================

Zuul 3 introduced tenant isolation, and most privileged actions, being scoped
to a specific tenant, reflect that change. However the only way to trigger
these actions is through the Zuul CLI, which assumes either access to the
environment of a Zuul component or to Zuul's configuration itself. This is a
problem as being allowed to perform privileged actions on a tenant should not
entice full access to Zuul's admin tasks.

.. Likewise, Nodepool provides actions that could be scoped to a tenant:

  * Ability to trigger an image build when the definition of an image used by
  that tenant has changed
  * Ability to delete nodesets that have been put on autohold (this is mitigated
  by the max-hold-age setting in Nodepool, if set)

  These actions can only be triggered through Nodepool's CLI, with the same
  problems as Zuul. Another important blocker is that Nodepool has no notion of
  tenancy as defined by Zuul.

Proposed Change
===============

Zuul will expose privileged actions through its web API. Assuming Zuul will be
served by a HTTP service that can handle authentication and set a unique Remote
User, authorization will be handled within Zuul by using oslo.policy.

Authorization with oslo.policy
------------------------------

Groups definition
.................

Zuul's zuul.conf will be extended to support deployment wide groups
definitions. Groups will be used to allow actions to specific users.

.. code-block:: ini

  [group admin]
    members = gozer
              slimer
              vigo

   [group ghostbusters2016]
    members = yates
              gilbert
              holtzmann


Likewise, Zuul's tenant configuration files will be extended to support
tenant-scoped groups definitions.

.. code-block:: YAML

    - tenant:
        name: my-tenant
        source:
          gerrit:
            config-projects:
              - common-config
            untrusted-projects:
              - project1
              - project2
        groups:
          - admin:
              members:
                - venkman
                - stantz
                - spengler
                - zeddemore
          - gozerians:
              members:
                - tully
                - dana

Groups can have any name. It is up to Zuul operators to inform tenant
maintainers of the groups that are used in policies.

The **members** list references values that are expected to be set in the
Remote-User field by the front-facing HTTP service.

Zuul's configuration will include a new policy file, consumable by oslo.policy.

The default rules will mirror the available web API routes, as follow:

.. code-block:: YAML

   "admin_or_tenant_admin": "group:admin or tenant.group:admin"

    "zuul:tenants": ""
    "zuul:tenant_info": ""
    "zuul:tenant_status": ""
    "zuul:tenant_jobs": ""
    "zuul:tenant_console_stream": ""
    "zuul:project_key": ""
    "zuul:buildset_enqueue": "rule:admin_or_tenant_admin"
    "zuul:job_autohold": "rule:admin_or_tenant_admin"
    "zuul:job_autohold_list": ""

oslo.policy will be extended within Zuul to support the following API
attributes checks:

* **user**: the remote user
* **tenant**: the target tenant
* **pipeline**: the target pipeline (if relevant)
* **group**: checks that the user is a member of the deployment wide group
* **tenant.group**: checks that the user is a member of the tenant scoped group
  in the target tenant. If the group is not defined within the target tenant,
  returns with failure
* **project.is_config**: returns with success if the target project is a config
  project for the target tenant

Web API changes
---------------

Zuul's web API will be extended to provide the following endpoints:

POST /api/tenant/{tenant}/project/{project}/pipeline/{pipeline}/enqueue
.......................................................................

This call allows a user to re-enqueue a buildset, like the *enqueue* or
*enqueue-ref* subcommands of Zuul's CLI.

To trigger the re-enqueue of a change, the following JSON body must be sent in
the query:

.. code-block:: javascript

    {"trigger": <Zuul trigger>,
     "change": <changeID>}

To trigger the re-enqueue of a ref, the following JSON body must be sent in
the query:

.. code-block:: javascript

    {"trigger": <Zuul trigger>,
     "ref": <ref>,
     "oldrev": <oldrev>,
     "newrev": <newrev>}

The call returns with HTTP status code 201 if successful, 401 if unauthorized,
400 with a JSON error description otherwise.

POST /api/tenant/{tenant}/project/{project}/job/{job}/autohold
..............................................................

This call allows a user to automatically put a node set on hold in case of
a build failure on the chosen job, like the *autohold* subcommand of Zuul's
CLI.

Any of the following JSON bodies must be sent in the query:

.. code-block:: javascript

    {"change": <changeID>,
     "reason": <reason>,
     "count": <count>,
     "node_hold_expiration": <expiry>}

or

.. code-block:: javascript

    {"ref": <ref>,
     "reason": <reason>,
     "count": <count>,
     "node_hold_expiration": <expiry>}

The call returns with HTTP status code 201 if successful, 401 if unauthorized,
400 with a JSON error description otherwise.

GET /api/tenant/{tenant}/project/{project}/job/{job}/autohold
.............................................................

This call allows a user to list existing autohold queries for a specific
tenant, project and job. Setting *{project}* or *{job}* to "*" will disable
filtering on this specific field.

The call returns a JSON list of autohold queries:

.. code-block:: javascript

    [{"tenant": "mytenant",
      "project": "project1",
      "job": "myjob",
      "ref_filter": ".*",
      "count": 1,
      "reason": "stay puft"}, ]

Web UI changes
--------------

The *builds.html* page will add a "re-enqueue" button at the end of each row,
allowing a user to re-enqueue a buildset based on the row's build.

A modal notification will inform the user of the success or failure of the
operation.

Implementation
==============

Assignee(s)
-----------

Primary assignee:
  mhu

.. feel free to add yourself as an assignee, the more eyes/help the better

Gerrit Topic
------------

Use Gerrit topic "zuul_admin_web" for all patches related to this spec.

.. code-block:: bash

    git-review -t zuul_admin_web

Work Items
----------

* Add the new endpoints to zuul web. This PoC needs to be reworked:
  https://review.openstack.org/#/c/539004/
* Add the policy engine, oslo.policy dependencies
* Web UI: add re-enqueue button to builds.html

Documentation
-------------

* The changes in the configuration will need to be documented.
* The additions to the web API needs to be documented.
* The requirement of having the HTTP service setting remote users when serving
  Zuul must be documented.

Security
--------

It is assumed deployments of Zuul will be done behind a HTTP service such as
Apache, specifically one that can handle user authentication and set remote
users. Deployments using the zuul webapp command require the default
policy rules to be overridden to allow or prevent access to the admin API.

The default policy rules for the admin actions could be **"!"**, ie not
allowed. The admin actions endpoints could be deactivated by default by a
configuration toggle until the police engine is merged into Zuul.

Testing
-------

* Unit testing of the new policy engine will be needed.
* Unit testing of the new web endpoints will be needed.
* Validation of the new configuration parameters will be needed.

Dependencies
============

This implementation will add a dependency to oslo.policy in Zuul.
