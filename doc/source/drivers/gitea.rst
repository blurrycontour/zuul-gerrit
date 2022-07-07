:title: Gitea Driver

.. _gitea_driver:

Gitea
=====

The Gitea driver supports sources, triggers, and reporters.  It can
interact with site-local installations of Gitea.

Configure Gitea
---------------

Each project to be integrated with Zuul needs:

- "Web hook target URL" set to
  http://<zuul-web>/zuul/api/connection/<conn-name>/payload
- Web hook "Trigger On" set to "All Events"
- Same Webhook Secret

In Gitea it is possible to set webhooks on the repository, organization or
system level.

Connection Configuration
------------------------

The supported options in ``zuul.conf`` connections are:

.. attr:: <gitea connection>

   .. attr:: driver
      :required:

      .. value:: gitea

         The connection must set ``driver=gitea`` for Gitea connections.

   .. attr:: webhook_secret

      The webhook secret used to sign events.

   .. attr:: api_token

      The user's API token.

   .. attr:: server
      :default: gitea.io

      Hostname of the Gitea server.

   .. attr:: canonical_hostname

      The canonical hostname associated with the git repos on the
      Gitea server.  Defaults to the value of :attr:`<gitea
      connection>.server`.  This is used to identify projects from
      this connection by name and in preparing repos on the filesystem
      for use by jobs.  Note that Zuul will still only communicate
      with the Gitea server identified by **server**; this option is
      useful if users customarily use a different hostname to clone or
      pull git repos so that when Zuul places them in the job's
      working directory, they appear under this directory name.

   .. attr:: baseurl
      :default: https://{server}:3000

      Path to the Gitea web and API interface.

   .. attr:: cloneurl
      :default: {baseurl}

      Omit to clone using http(s) or set to ``ssh://git@{server}``.
      If **api_token** is set and **cloneurl** is either omitted or is
      set without credentials, **cloneurl** will be modified to use credentials
      as this: ``http(s)://git:<api_token>@<server>``.
      If **cloneurl** is defined with credentials, it will be used as is,
      without modification from the driver.

   .. attr:: sshkey

      Path to SSH key to use (Used if **cloneurl** is ssh)

Trigger Configuration
---------------------
Gitea webhook events can be configured as triggers.

A connection name with the Gitea driver can take multiple events with
the following options.

.. attr:: pipeline.trigger.<gitea source>

   The dictionary passed to the Gitea pipeline ``trigger`` attribute
   supports the following attributes:

   .. attr:: event
      :required:

      The event from Gitea. Supported events are:

      .. value:: gt_pull_request

      .. value:: gt_push

   .. attr:: action

      A :value:`pipeline.trigger.<gitea source>.event.gt_pull_request`
      event will have associated action(s) to trigger from. The
      supported actions are:

      .. value:: opened

         Pull request opened.

      .. value:: changed

         Pull request synchronized.

      .. value:: closed

         Pull request closed.

      .. value:: comment

         Comment added to pull request.

      .. value:: status

         Status set on pull request.

      .. value:: tagged

         Tag metadata set on pull request.


Reference pipelines configuration
---------------------------------

Here is an example of standard pipelines you may want to define:

.. literalinclude:: /examples/pipelines/gitea-reference-pipelines.yaml
   :language: yaml
