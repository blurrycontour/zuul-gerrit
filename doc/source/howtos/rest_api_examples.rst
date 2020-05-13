:title: REST API examples using cURL

.. _rest-api-examples:

Using the REST API with cURL
============================

Here are some examples of how Zuul's REST API can be used with cURL.

Prerequisites
-------------

* cURL must be installed on your system.
* Privileged actions such as enqueue or autohold require a valid authentication
  token. Zuul operators can generate tenant-scoped tokens for users
  by following instructions in the section :ref:`tenant-scoped-rest-api`.

For readability, let's assume the authentication token is stored in a shell variable
called `TOKEN`, and the base URL of the Zuul deployment in `ZUUL_URL`.

Autohold
--------

Hold nodes for 10 hours the first time job `test-job-tox-sudoless-el8` fails
on any change on project `third-party-ci-jobs` belonging to tenant `opendev.org`:

.. code-block:: bash

  curl -X POST \
       -H "Authorization: bearer "$TOKEN \
       -H "Content-type: application/json" \
       $ZUUL_URL/api/tenant/opendev.org/project/third-party-ci-jobs/autohold \
       --data '{"reason": "because", "count": 1, "job": "test-job-tox-sudoless-el8", "change": "", "ref": "", "node_hold_expiration": 36000}'

Autohold (info)
---------------

Get the list of autohold requests currently active on tenant `ghostbusters`:

.. code-block:: bash

  curl $ZUUL_URL/api/tenant/ghostbusters/autohold

Get details on a specific request by its id (example: 1234):

.. code-block:: bash

  curl $ZUUL_URL/api/tenant/ghostbusters/autohold/1234

Autohold (delete)
-----------------

Delete an autohold request with id 4321 on tenant `slimer`:

.. code-block:: bash

  curl -X DELETE \
       -H "Authorization: bearer "$TOKEN \
       $ZUUL_URL/api/tenant/slimer/autohold/4321

Enqueue
-------

Trigger the periodic pipeline jobs at the tip of master for project `staypuft`
belonging to tenant `gozerians`:

.. code-block:: bash

  curl -X POST \
       -H "Authorization: bearer "$TOKEN \
       -H "Content-type: application/json" \
       $ZUUL_URL/api/tenant/gozerians/project/staypuft/enqueue \
       --data '{"ref": "master", "oldrev": "0000000000000000000000000000000000000000", "newrev": "0000000000000000000000000000000000000000", "pipeline": "periodic"}'

Dequeue
-------

Stop the ongoing buildset for change/patchset 1234/5 on project `deadbeef` in
tenant `hexadecimalprojects`, in the check pipeline:

.. code-block:: bash

 curl -X POST \
      -H "Authorization: bearer "$TOKEN \
      -H "Content-type: application/json" \
      $ZUUL_URL/api/tenant/hexadecimalprojects/project/deadbeef/dequeue \
      --data '{"pipeline": "check", "change": "1234,5"}'
