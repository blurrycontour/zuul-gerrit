:title: Slack Driver

Slack
=====

The Slack driver supports reporters only.  It is used to send chat messages
when items report.

Connection Configuration
------------------------

.. attr:: <slack connection>

   .. attr:: driver
      :required:

      .. value:: slack

         The connection must set ``driver=slack`` for Slack connections.

   .. attr:: token

      Slack API token to use. There are numerous was to obtain one of these.
      It's recommended to create a bot_ integration and invite the bot to the
      listed channels.

   .. attr:: subject

      Default subject for messages from this connection.

.. _bot: https://api.slack.com/bot-users

Reporter Configuration
----------------------

A :ref:`connection<connections>` that uses the slack driver must be supplied to the
reporter.

Each pipeline can set the ``subject`` to use for the initial
non-threaded message. The body of the report will be set as a reply
in this thread to avoid vertically spamming channels.

Each pipeline can also set specific project channel mappings. All
messages will be sent to ``channel``, which can be a list of strings,
or a single string.

This pipeline sends all messages to ``#post-merge`` and messages for
the ``sandbox`` project to ``#sandbox``:

.. code-block:: yaml

   - pipeline:
       name: post-merge
       success:
         team_slack:
           channel: '#post-merge'
           project_channels:
             - project: sandbox
               channel: '#sandbox'
       failure:
         team_slack:
           channel: '#post-merge'
           project_channels:
             - project: sandbox
               channel: '#sandbox'

.. attr:: pipeline.<reporter>.<slack source>

   To report via slack, the dictionaries passed to any of the pipeline
   :ref:`reporter<reporters>` attributes support the following
   attributes:

   .. attr:: channel

      A channel or a list of channels to send all messages to.

   .. attr:: project-channels

      A list of dicts to send specific project messages to.

      .. attr:: project

         String that will match the name of the project.

      .. attr:: channel
      
         String that indicates what channel to send this project messages to.

   .. attr:: subject

      The Subject of the report message.

      .. TODO: document subject string formatting.
