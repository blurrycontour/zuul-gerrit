:title: Bitbucket Server Driver

.. bitbucket_driver:

Bitbucket Server
================

The Bitbucket Server driver supports sources. It is primarily intended
to interact with Bitbucket Server instances, i.e. not useful for the
Bitbucket Cloud offering.

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

Connection configuration
------------------------

Zuul can report back build status to Bitbucket, it will do this on a
per pipeline basis. This feature is based on the Bitbucket build
status API. Build status can be used to set conditions in Bitbucket
like all other build information can be used. Reporting includes
the pipeline name and the string "Zuul".

There are no configuration items right now.
