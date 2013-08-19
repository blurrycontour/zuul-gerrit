:title: Reporters

Reporters
========

Zuul can communicate results and progress back to configurable
protocols. For example, after succeeding in a build a pipeline can be
configured to post a positive review back to gerrit.

There are three stages when a report can be handled. That is on:
Start, Success or Failure. Each stage can have multiple reports.
For example, you can set verified on gerrit and send an email.

Gerrit
------

Zuul works with standard versions of Gerrit by invoking the ``gerrit
stream-events`` command over an SSH connection.  It reports back to
Gerrit using SSH.

Gerrit Configuration
~~~~~~~~~~~~~~~~~~~~

The configuration for posting back to gerrit is shared with the gerrit
trigger documentation.

SMTP
-----

A simple email reporter is also available. The defaults can be set in
the zuul.conf file or overwritten in the pipeline.