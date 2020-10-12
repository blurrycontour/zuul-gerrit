:title: Bitbucket Server Driver

.. _bitbucketserver_driver/

Bitbucket Server
================

The Bitbucket Server driver supports sources and triggers.

Configure Bitbucket server
----------------

Zuul needs to interact with projects by:

- receiving events via web-hooks
- performing actions via the API

The Zuul user's API token configured in zuul.conf must have the admin rights.

Each project to be integrated with Zuul needs in "Repository settings/Webhooks":

- "URL" set to
  ``http://<zuul-web>/api/connection/<conn-name>/payload``

It is recommended to enable following events for `Repository` and `Pull request`
- Push
- Opened
- Source branch updated
- Modified
- Approved
- Unapproved
- Needs work
- Pulld
- Declined
- Deleted
- Comment added

Connection Configuration
------------------------

The supported options in ``zuul.conf`` connections are:

.. attr:: <bitbucketserver connection>

   .. attr:: driver
      :required:

      .. value:: bitbucketserver

         The connection must set ``driver=bitbucketserver`` for Bitbucket server connections.

   .. attr:: user

      The API user name.

   .. attr:: password

      The API user password.

   .. attr:: baseurl
      :default: https://{server}

      Path to the Bitbucket server API interface.

Trigger Configuration
---------------------

Bitbucket server webhook events can be configured as triggers.

A connection name with the Bitbucket server driver can take multiple events with
the following options.

.. attr:: pipeline.trigger.<bitbucketserver source>

   The dictionary passed to the Bitbucket server pipeline ``trigger`` attribute
   supports the following attributes:

   .. attr:: event
      :required:

      The event from Bitbucket server. Supported events are:

      .. value:: pull_request

      .. value:: repository

   .. attr:: action

      A :value:`pipeline.trigger.<bitbucketserver source>.event.pull_request`
      event will have associated action(s) to trigger from. The
      supported actions are:

      .. value:: opened

         A pull request is opened or reopened.

      .. value:: updated

         A pull request's source branch has been updated.

      .. value:: modified

         A pull request's description, title, or target branch is changed.

      .. value:: reviewers_updated

         A pull request's reviewers have been added or removed.

      .. value:: approved

         A pull request is marked as approved by a reviewer.

      .. value:: unapproved

         A pull request is unapproved by a reviewer.

      .. value:: needs_work

         A pull request is marked as needs work by a reviewer.

      .. value:: merged

         A pull request is merged.

      .. value:: declined

          A pull request is declined.

   .. attr:: ref

      This is only used for ``push`` events. This field is treated as
      a regular expression and multiple refs may be listed. Bitbucket server
      always sends full ref name, eg. ``refs/heads/bar`` and this
      string is matched against the regular expression.


Requirements Configuration
--------------------------

As described in :attr:`pipeline.require` pipelines may specify that items meet
certain conditions in order to be enqueued into the pipeline.  These conditions
vary according to the source of the project in question.

.. code-block:: yaml

   pipeline:
     require:
       bitbucketserver:
         open: true

This indicates that changes originating from the Bitbucket server connection must be
in the *opened* state (not merged yet).

.. attr:: pipeline.require.<bitbucketserver source>

   The dictionary passed to the Bitbucket server pipeline `require` attribute
   supports the following attributes:

   .. attr:: open

      A boolean value (``true`` or ``false``) that indicates whether
      the Pull Request must be open in order to be enqueued.

   .. attr:: merged

      A boolean value (``true`` or ``false``) that indicates whether
      the Pull Request must be merged or not in order to be enqueued.

   .. attr:: approved

      A boolean value (``true`` or ``false``) that indicates whether
      the Pull Request must be approved or not in order to be enqueued.