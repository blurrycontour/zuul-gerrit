:title: Reporters

Reporters
=========

Zuul can communicate results and progress back to configurable
protocols. For example, after succeeding in a build a pipeline can be
configured to post a positive review back to Gerrit.

There are three stages when a report can be handled. That is on:
Start, Success or Failure. Each stage can have multiple reports.
For example, you can set verified on Gerrit and send an email.

Fedmsg
------

fedmsg (FEDerated MeSsaGe bus) is a brokerless messaging architecture
to send and receive messages to and from applications.  For more information
we encourage you to read about it at http://www.fedmsg.com/.

A :ref:`connection` that uses the fedmsg driver must be supplied to the
trigger.

Fedmsg Configuration
~~~~~~~~~~~~~~~~~~~~

fedmsg has its own configuration management system. As a result, fedmsg
configuration should be added into the /etc/fedmsg.d folder. Specific settings
can be found in the fedmsg documentation
http://www.fedmsg.com/en/latest/config/#module-fedmsg.config

Each pipeline can define a separate topic to publish messages. EG::

  pipelines:
    - name: post-merge
      manager: IndependentPipelineManager
      source: my_gerrit
      trigger:
        my_gerrit:
          - event: change-merged
      success:
        fedmsg:
          topic: public
      failure:
        fedmsg:
          topic: private


Gerrit
------

Zuul works with standard versions of Gerrit by invoking the
``gerrit`` command over an SSH connection.  It reports back to
Gerrit using SSH.

The dictionary passed to the Gerrit reporter is used for ``gerrit
review`` arguments, with the boolean value of ``true`` simply
indicating that the argument should be present without following it
with a value. For example, ``verified: 1`` becomes ``gerrit review
--verified 1`` and ``submit: true`` becomes ``gerrit review
--submit``.

A :ref:`connection` that uses the gerrit driver must be supplied to the
trigger.

SMTP
----

A simple email reporter is also available.

A :ref:`connection` that uses the smtp driver must be supplied to the
trigger.

SMTP Configuration
~~~~~~~~~~~~~~~~~~

zuul.conf contains the SMTP server and default to/from as described
in :ref:`zuulconf`.

Each pipeline can overwrite the ``subject`` or the ``to`` or ``from`` address by
providing alternatives as arguments to the reporter. For example, ::

  pipelines:
    - name: post-merge
      manager: IndependentPipelineManager
      source: my_gerrit
      trigger:
        my_gerrit:
          - event: change-merged
      success:
        outgoing_smtp:
          to: you@example.com
      failure:
        internal_smtp:
          to: you@example.com
          from: alternative@example.com
          subject: Change {change} failed
