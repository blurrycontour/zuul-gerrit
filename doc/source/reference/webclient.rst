:title: Zuul Web Client

Zuul Web Client
===============

Zuul includes a simple command line client that may be used to query Zuul's
state or affect its behavior, granted the user is allowed to do so. It must be
run on a host with access to Zuul's web server.

Configuration
-------------

The web client will look by default for a ``/etc/zuul/zuul.conf`` file for its
configuration. The file should consist of a ``[webclient]`` section with at least
the ``url`` attribute set. The optional ``verify_ssl`` can be set to False to
disable SSL verifications when connecting to Zuul (defaults to True).

It is also possible to run the web client without a configuration file, by using the
``--zuul-url`` option to specify the base URL of the Zuul web server.

Privileged commands
-------------------

Some commands require a valid authentication token to be passed as the ``--auth-token``
argument. Administrators can generate such a token for users by following instructions
as described in the section :ref:`tenant-scoped-rest-api`.

Usage
-----
The general options that apply to all subcommands are:

.. program-output:: zuul-web-client --help

The following subcommands are supported:

Autohold
^^^^^^^^

.. note:: This command is only available with a valid authentication token.

.. program-output:: zuul-web-client autohold --help

Example::

  zuul-web-client autohold --tenant openstack --project example_project --job example_job --reason "reason text" --count 1

Autohold Delete
^^^^^^^^^^^^^^^

.. note:: This command is only available with a valid authentication token.

.. program-output:: zuul-web-client autohold-delete --help

Example::

  zuul-web-client autohold-delete --tenant openstack --id 0000000123

Autohold Info
^^^^^^^^^^^^^
.. program-output:: zuul-web-client autohold-info --help

Example::

  zuul-web-client autohold-info --tenant openstack --id 0000000123

Autohold List
^^^^^^^^^^^^^
.. program-output:: zuul-web-client autohold-list --help

Example::

  zuul-web-client autohold-list --tenant openstack

Dequeue
^^^^^^^

.. note:: This command is only available with a valid authentication token.

.. program-output:: zuul-web-client dequeue --help

Examples::

    zuul-web-client dequeue --tenant openstack --pipeline check --project example_project --change 5,1
    zuul-web-client dequeue --tenant openstack --pipeline periodic --project example_project --ref refs/heads/master

Enqueue
^^^^^^^

.. note:: This command is only available with a valid authentication token.

.. program-output:: zuul-web-client enqueue --help

Example::

  zuul-web-client enqueue --tenant openstack --trigger gerrit --pipeline check --project example_project --change 12345,1

Note that the format of change id is <number>,<patchset>.

Enqueue-ref
^^^^^^^^^^^

.. note:: This command is only available with a valid authentication token.

.. program-output:: zuul-web-client enqueue-ref --help

This command is provided to manually simulate a trigger from an
external source.  It can be useful for testing or replaying a trigger
that is difficult or impossible to recreate at the source.  The
arguments to ``enqueue-ref`` will vary depending on the source and
type of trigger.  Some familiarity with the arguments emitted by
``gerrit`` `update hooks
<https://gerrit-review.googlesource.com/admin/projects/plugins/hooks>`__
such as ``patchset-created`` and ``ref-updated`` is recommended.  Some
examples of common operations are provided below.

Manual enqueue examples
***********************

It is common to have a ``release`` pipeline that listens for new tags
coming from ``gerrit`` and performs a range of code packaging jobs.
If there is an unexpected issue in the release jobs, the same tag can
not be recreated in ``gerrit`` and the user must either tag a new
release or request a manual re-triggering of the jobs.  To re-trigger
the jobs, pass the failed tag as the ``ref`` argument and set
``newrev`` to the change associated with the tag in the project
repository (i.e. what you see from ``git show X.Y.Z``)::

  zuul-web-client enqueue-ref --tenant openstack --trigger gerrit --pipeline release --project openstack/example_project --ref refs/tags/X.Y.Z --newrev abc123...

The command can also be used asynchronosly trigger a job in a
``periodic`` pipeline that would usually be run at a specific time by
the ``timer`` driver.  For example, the following command would
trigger the ``periodic`` jobs against the current ``master`` branch
top-of-tree for a project::

  zuul-web-client enqueue-ref --tenant openstack --trigger timer --pipeline periodic --project openstack/example_project --ref refs/heads/master

Another common pipeline is a ``post`` queue listening for ``gerrit``
merge results.  Triggering here is slightly more complicated as you
wish to recreate the full ``ref-updated`` event from ``gerrit``.  For
a new commit on ``master``, the gerrit ``ref-updated`` trigger
expresses "reset ``refs/heads/master`` for the project from ``oldrev``
to ``newrev``" (``newrev`` being the committed change).  Thus to
replay the event, you could ``git log`` in the project and take the
current ``HEAD`` and the prior change, then enqueue the event::

  NEW_REF=$(git rev-parse HEAD)
  OLD_REF=$(git rev-parse HEAD~1)

  zuul-web-client enqueue-ref --tenant openstack --trigger gerrit --pipeline post --project openstack/example_project --ref refs/heads/master --newrev $NEW_REF --oldrev $OLD_REF

Note that zero values for ``oldrev`` and ``newrev`` can indicate
branch creation and deletion; the source code is the best reference
for these more advanced operations.


Promote
^^^^^^^

.. note:: This command is only available with a valid authentication token.

.. program-output:: zuul-web-client promote --help

This command will push the listed changes at the top of the chosen pipeline.

Example::

  zuul-web-client promote --tenant openstack --pipeline check --changes 12345,1 13336,3

Note that the format of changes id is <number>,<patchset>.

console-stream
^^^^^^^^^^^^^^

.. program-output:: zuul-web-client console-stream --help

This command streams the console log of an ongoing job for a given change.
`Change` is in the form "change_number,patchset" (gerrit) or
"pull_request,commithash" (github).
