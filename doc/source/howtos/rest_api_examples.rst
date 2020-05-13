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

Get the list of autohold requests currently active on tenant `opendev`:

.. code-block:: bash

  curl $ZUUL_URL/api/tenant/opendev/autohold

Get details on a specific request by its id (example: 1234):

.. code-block:: bash

  curl $ZUUL_URL/api/tenant/opendev/autohold/1234

Autohold (delete)
-----------------

Delete an autohold request with id 4321 on tenant `openstack`:

.. code-block:: bash

  curl -X DELETE \
       -H "Authorization: bearer "$TOKEN \
       $ZUUL_URL/api/tenant/openstack/autohold/4321

Enqueue
-------

The enqueue endpoint requires distinct arguments depending on the target pipeline's
post-review attribute. For more information about this attribute, see
:attr:`pipeline.post-review`.

Post-review pipelines
*********************

Trigger the periodic pipeline jobs at the tip of master for project `opendev.org/zuul/zuul-jobs`
belonging to tenant `zuul`:

.. code-block:: bash

  curl -X POST \
       -H "Authorization: bearer "$TOKEN \
       -H "Content-type: application/json" \
       $ZUUL_URL/api/tenant/zuul/project/opendev.org/zuul/zuul-jobs/enqueue \
       --data '{"ref": "master", "oldrev": "0000000000000000000000000000000000000000", "newrev": "0000000000000000000000000000000000000000", "pipeline": "periodic"}'

The dummy value `0000000000000000000000000000000000000000` points to ref's HEAD
commit.

pre-review pipelines
********************

Re-enqueueing a change on a pre-review pipeline should be possible via the code
review system hosting that change (for example, by commenting *recheck* on a
change on https://review.opendev.org). If for some reason it is necessary to
re-enqueue pre-review jobs for a given change via Zuul's REST API, adapt the
following example:

Trigger the check pipeline jobs for change 12345,2 on project `opendev.org/zuul/zuul-jobs`
belonging to tenant `zuul`:

.. code-block:: bash

  curl -X POST \
       -H "Authorization: bearer "$TOKEN \
       -H "Content-type: application/json" \
       $ZUUL_URL/api/tenant/zuul/project/opendev.org/zuul/zuul-jobs/enqueue \
       --data '{"change": "12345,2", "pipeline": "check"}'


Dequeue
-------

Stop the ongoing buildset for change/patchset 1234,5 on project `deadbeef` in
tenant `hexadecimalprojects`, in the check pipeline:

.. code-block:: bash

 curl -X POST \
      -H "Authorization: bearer "$TOKEN \
      -H "Content-type: application/json" \
      $ZUUL_URL/api/tenant/hexadecimalprojects/project/deadbeef/dequeue \
      --data '{"pipeline": "check", "change": "1234,5"}'
