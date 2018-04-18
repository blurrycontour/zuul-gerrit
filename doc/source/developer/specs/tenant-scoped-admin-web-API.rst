===========================
Tenant-scoped admin web API
===========================

https://storyboard.openstack.org/#!/story/2001771

The aim of this spec is to extend the existing web API of Zuul to
privileged actions, and to scope these actions to tenants, projects and privileged users.

Problem Description
===================

Zuul 3 introduced tenant isolation, and most privileged actions, being scoped
to a specific tenant, reflect that change. However the only way to trigger
these actions is through the Zuul CLI, which assumes either access to the
environment of a Zuul component or to Zuul's configuration itself. This is a
problem as being allowed to perform privileged actions on a tenant or for a
specific project should not entice full access to Zuul's admin capabilities.

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

Zuul will expose privileged actions through its web API. A JWT (JSON Web Token)
will be used to carry information about tenants and projects on which a user
can perform administration tasks.

A Zuul operator can generate a JWT with the right scope for a user, and communicate
the JWT to said user. By querying Zuul's web API with the Token set in an
"Authorization" header, the user can perform administration tasks.

Zuul will need to provide the following minimal new features:

* JWT generation
* JWT validation
* administration web API

JWT Generation
--------------

Format
......

The Token's contents will have the following format:

.. code-block:: javascript

  {
   'exp': 1234567890,
   'sub': 'venkman',
   'zuul.actions': {
       'enqueue': {
           'tenantA': ['org/project1', 'org/project2'],
           'tenantB': '*',
       },
       'dequeue': '*',
       'autohold': {
           'tenantA': ['org/project1', 'org/project2'],
           'tenantB': '*',
       },
   }
  }

Note that JWTs can be arbitrarily extended with new claims further down the road,
or fused with JWTs issued by other services thanks to the isolation
provided by the "zuul.*" namespace.

* **exp** is the token's expiry timestamp.
* **sub** [optional] is the identifier of the user. While optional, this should
  be used for traceability during logging.
* **zuul.actions** is a dictionary where the keys are available privileged
  actions. These in turn store dictionaries where keys are tenants, or '\*'
  wildcard value indicating that the user can perform the action on every tenant and their related projects.
* **Action dictionaries** use tenants as keys, and the values can either be
  a list of projects on which the user can perform administration tasks;
  or the '\*' wildcard meaning that the user can perform such actions on
  every project of the tenant.

In the former example, user **venkman** can perform privileged actions
"enqueue" and "autohold" on every project of **tenantB** and
projects **org/project1**, **org/project2** of **tenantA**; **venkman** can
also dequeue jobs on **every tenant**.

These are intended to be **whitelists**: if an action is unlisted the user is
assumed not to be allowed to perform the action; and so on at the tenant and
project levels.

Client CLI
..........

A new command will be added to the Zuul Client CLI to allow an operator to generate
a JWT for a third party. It will return the contents of the ``Authorization`` header
as it should be set when querying the admin web API.

.. code-block:: bash

  $ zuul create-token --user venkman --tenant tenantA --project org/project1 --project org/project2 --expires-in 1800
  bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwOi8vbWFuYWdlc2Yuc2ZyZG90ZXN0aW5zdGFuY2Uub3JnIiwienV1bC50ZW5hbnRzIjp7ImxvY2FsIjoiKiJ9LCJleHAiOjE1Mzc0MTcxOTguMzc3NTQ0fQ.DLbKx1J84wV4Vm7sv3zw9Bw9-WuIka7WkPQxGDAHz7s

Configuration Changes
.....................

The admin web API can be enabled in the web configuration section.

JWT creation requires a secret and an algorithm. Supported algorithms are those
supported by the pyJWT library as listed here: https://pyjwt.readthedocs.io/en/latest/algorithms.html

.. code-block:: ini

  [web]
  listen_address=127.0.0.1
  port=9000
  static_cache_expiry=0
  status_url=https://zuul.example.com/status
  # Admin API
  enable_admin_endpoints=True
  JWTsecret=NoDanaOnlyZuul
  JWTalgorithm=HS256

JWT Validation
--------------

A decorator can be added to cherrypy.tools to protect selected web API endpoints
with a JWT. The decorator will be in charge of decoding the JWT and validating
its contents (expiry, scope).

Administration Web API
----------------------

All the following endpoints require the presence of the ``Authorization`` header
in the HTTP query, or adding a query string called ``jwt`` to the HTTP query.

Zuul's web API will be extended to provide the following endpoints:

POST /api/tenant/{tenant}/project/{project}/enqueue
...................................................

This call allows a user to re-enqueue a buildset, like the *enqueue* or
*enqueue-ref* subcommands of Zuul's CLI.

To trigger the re-enqueue of a change, the following JSON body must be sent in
the query:

.. code-block:: javascript

    {"trigger": <Zuul trigger>,
     "change": <changeID>,
     "pipeline": <pipeline>}

To trigger the re-enqueue of a ref, the following JSON body must be sent in
the query:

.. code-block:: javascript

    {"trigger": <Zuul trigger>,
     "ref": <ref>,
     "oldrev": <oldrev>,
     "newrev": <newrev>,
     "pipeline": <pipeline>}

The call returns with HTTP status code 201 if successful, 401 if unauthorized,
400 with a JSON error description otherwise.

POST /api/tenant/{tenant}/project/{project}/dequeue
...................................................

This call allows a user to dequeue a buildset, like the *dequeue* subcommand of
Zuul's CLI.

To dequeue a change, the following JSON body must be sent in the query:

.. code-block:: javascript

    {"change": <changeID>,
     "pipeline": <pipeline>}

To dequeue a ref, the following JSON body must be sent in
the query:

.. code-block:: javascript

    {"ref": <ref>,
     "pipeline": <pipeline>}

The call returns with HTTP status code 201 if successful, 401 if unauthorized,
400 with a JSON error description otherwise.

POST /api/tenant/{tenant}/project/{project}/autohold
..............................................................

This call allows a user to automatically put a node set on hold in case of
a build failure on the chosen job, like the *autohold* subcommand of Zuul's
CLI.

Any of the following JSON bodies must be sent in the query:

.. code-block:: javascript

    {"change": <changeID>,
     "reason": <reason>,
     "count": <count>,
     "node_hold_expiration": <expiry>,
     "job": <job>}

or

.. code-block:: javascript

    {"ref": <ref>,
     "reason": <reason>,
     "count": <count>,
     "node_hold_expiration": <expiry>,
     "job": <job>}

The call returns with HTTP status code 201 if successful, 401 if unauthorized,
400 with a JSON error description otherwise.


Logging
.......

If the ``sub`` claim is set, the call to the web API will be logged with the value
of the ``sub`` claim.

Zuul Client CLI and Admin Web API
.................................

The client CLI can be modified to accept an optional --jwt argument on the ``autohold``,
``enqueue``, ``enqueue-ref`` and ``dequeue`` commands. if the JWT is passed to
the CLI, the CLI will query the web API to execute these commands rather than
using RPC; allowing non-privileged users to use the CLI remotely.

.. code-block:: bash

  $ zuul autohold --tenant openstack --project example_project --job example_job --reason "reason text" --count 1 --jwt AaAa....
  Connecting to https://zuul.openstack.org...
  <usual autohold output>


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

* https://review.openstack.org/#/c/576907 : PoC

Documentation
-------------

* The changes in the configuration will need to be documented.
* The additions to the web API need to be documented.
* The additions to the Zuul Client CLI need to be documented.

Security
--------

Anybody with a valid JWT can perform administration tasks exposed through the
Web API. Revoking JWT is not trivial, and not in the scope of this spec.

As a mitigation, JWTs should be generated with a short time to live, like 30
minutes or less. This could be the default value for the CLI. JWTs should also
be generated with as little a scope as possible (one tenant and one project) to
reduce the surface of attack should the Token be compromised.

Exposing administration tasks can impact build results (dequeue-ing buildsets),
and pose potential resources problems in Nodepool if the ``autohold`` feature
is abused. Such tokens should be handed over responsibly.

These security considerations concern operators and the way they handle this
feature, and do not impact development.

Testing
-------

* Unit testing of the new web endpoints will be needed.
* Validation of the new configuration parameters will be needed.

Dependencies
============

This implementation will use an existing dependency to pyJWT in Zuul.
