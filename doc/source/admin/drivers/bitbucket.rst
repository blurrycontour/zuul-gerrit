:title: Bitbucket Server Driver

.. bitbucket_driver:

Bitbucket Server
================

The Bitbucket Server driver supports sources, reporters and triggers.
It is primarily intended to interact with Bitbucket Server instances,
i.e. not useful for the Bitbucket Cloud offering.

Configure Bitbucket Server
--------------------------

You need to generate a user on Bitbucket that can read and write all
relevant projects and repositories. Furthermore you need to
register a SSH keypair for this user and distribute it to your
Zuul nodes.

Connection configuration
------------------------

The Bitbucket Server source will connect to a Bitbucket Server instance
via a named user. The options for the ``zuul.conf`` connections are:

.. attr:: <bitbucket connection>

  .. attr:: driver
    :required:

    .. value:: bitbucket

      The connection requires ``driver=bitbucket`` for Bitbucket Server
      connections.

  .. attr:: baseurl
    :required:

    The base URL of the Bitbucket API. E.g. ``https://bitbucket.foo.test``

  .. attr:: cloneurl
     :required:

    The base URL of the Bitbucket GIT. E.g. ``ssh://git@bitbucket.foo.test:5999``

  .. attr:: user
    :required:

    Username to log in to the server.

  .. attr:: password
    :required:

    Password for the user to log in to the server.

  .. attr:: canonical_hostname

    Set canonical hostname, defaults to the hostname and port in the ``baseurl``.

Reporter configuration
------------------------

Zuul can report back build status to Bitbucket, it will do this on a
per pipeline basis. This feature is based on the Bitbucket build
status API. Build status can be used to set conditions in Bitbucket
like all other build information can be used. Reporting includes
the pipeline name and the string "Zuul".


.. attr:: pipeline.<reporter>.<bitbucket source>

   To report to Bitbucket, the dictionaries passed to any of the pipeline
   :ref:`reporter<reporters>` attributes support the following
   attributes:

   .. attr:: merge
      :default: False

      Boolean value that determines if the reporter should merge
      the pull request.

   .. attr:: label
      :default: Zuul

      String value for a label URL to set in the build status.
      Build status will include the report text prefixed by this
      label.

    .. attr:: reportid
      :default: zuul

      String value that acts as a prefix to the not user visible
      id of the build status. This can be useful if you use multiple
      Zuul servers that report.

Trigger configuration
---------------------

Zuul can trigger on multiple conditions:

.. attr:: pipeline.trigger.<bitbucket source>

  The dictionary passed to the pipeline via the ``trigger`` attribute
  suppots the following attributes:

  ..attr:: event
    :required:

    The event from Bitbucket. The following events are supported:

    .. value:: bb-pr

    A pull request has been updated or created.

    .. value:: bb-comment

    A comment was added to a pull request.

    .. value:: bb-push

    A branch received a push.

    .. value:: bb-tag

    A tag has been pushed.

  .. attr:: action
    :required:

    The action performed.

    .. value:: opened

    A pull request has been opened.

    .. value:: updated

    A pull request has been updated, a comment has been created, or a
    branch/tag was pushed.

  .. attr:: branch

    This is used for ``bb-pr``, ``bb-branch`` and ``bb-tag`` events. It signifies
    the branch the event happens on or the branch the pull request wants
    to merge to.

  .. attr:: comment

    This is only set on ``bb-comment`` events, it's the comment's contents.

  .. attr:: ref

    This is set on ``bb-pr``, ``bb-branch`` and ``bb-tag`` events. It is the
    git ref that is being changed, i.e. the source branch (on a PR) or the
    branch or tag that is being pushed.

Requirements configuration
--------------------------

As described in :attr:`pipeline.require` pipelines may specify that items meet
certain conditions in order to be enqueued into the pipeline.  These conditions
vary according to the source of the project in question.  To supply
requirements for changes from a Bitbucket source named ``bitbucket``, create a
configuration such as the following::

  - pipeline:
      name: gate
      manager: independent
      require:
        bitbucket:
          canMerge: True
          open: True

Contrary to other drivers, the Bitbucket driver does not expose review count or
successful builds to Zuul. Instead it uses the Bitbucket API to check if the
pull request can merge. This way you can use Bitbucket's built-in merge checks
to make sure that pull requests can merge.

  .. attr: open

    Whether the change is open.

  .. attr: closed

    Whether the change is closed.

  .. attr: status

    The status of the change. Either ``OPEN`` or ``MERGED``

  .. attr: canMerge

    Whether the change can merge.

Reference pipeline configuration
--------------------------------

Here is an example of a standard pipeline you can define::

  - pipeline:
      name: check
      manager: independent
      require:
        bitbucket:
          canMerge: False
          open: True
      trigger:
        bitbucket:
          - event: bb-comment
            action: 
              - updated
            comment: (?i)^\s*recheck\s*$
          - event: bb-pr
            action:
              - opened
              - updated
      success:
        bitbucket:
          merge: False
      failure:
        bitbucket:
          merge: False

  - pipeline:
      name: gate
      manager: independent
      require:
        bitbucket:
          canMerge: True
          open: True
      trigger:
        bitbucket:
          - event: bb-pr
            action:
              - updated
          - event: bb-comment
            action: 
              - updated
            comment: (?i)^\s*recheck\s*$
      success:
        bitbucket:
          merge: True
      failure:
        bitbucket:
          merge: False

  - pipeline:
      name: post
      post-review: true
      manager: independent
      trigger:
        bitbucket:
          - event: bb-push
            ref: ^refs/heads/master.*$
