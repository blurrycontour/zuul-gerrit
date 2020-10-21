:title: Bitbucket Cloud Driver

.. _bitbucketcloud_driver:

Bitbucket Cloud
===============

The Bitbucket Cloud driver supports sources, triggers, and reporters.  It
interacts with publically hosted Bitbucket Cloud repositories.

Configure Bitbucket Cloud
-------------------------

Currently the supported option is to configure webhook integrations for each
repository and to supply Zuul with a user account that has permissions to
perform api actions upon the repository.


Webhook configuration
.....................

To configure a project's `webhook events
<https://support.atlassian.com/bitbucket-cloud/docs/manage-webhooks/>`_:

* Set *Title* to be identifiable to the Zuul connection.

* Set *URL* to
  ``http://<zuul-hostname>:<port>/api/connection/<connection-name>/payload``.

* Do not tick *Skip certificate verification*

* Select *Choose from a full list of triggers*

Select all *Events* that are required for the Zuul integration. The list of
supported events are:

- Repository Push
- Repository Updated
- Pull Request Created
- Pull Request Updated
- Pull Request Comment created


A Bitbucket Cloud user should be created with access to *Read* and *Write* to
every project in the Zuul connection:

* This user needs an SSH key created for their account, see this `doc <https://support.atlassian.com/bitbucket-cloud/docs/set-up-an-ssh-key/>`_
  with the public key stored in the Bitbucket Cloud user interface, and the
  private key stored in Zuuls configuration (see below).

* An *App password* needs to be created for the user, see this `article
  <https://support.atlassian.com/bitbucket-cloud/docs/app-passwords>`_
  Select Read & Write for Pull requests, Projects and Repositories.

The private key and app password will need to be configured on the Zuul
instance (see connection configuration).

Webhook security
................

Bitbucket Cloud does not support any means off authenticating webhook event
payloads, it is therefore advised to ensure the use of ssl for requests.


Furthermore it is advised to lockdown the Zuul webhook endpoint to the list of
Bitbucket Cloud IP ranges using a loadbalancer firewall rule or equivalent.
The current list of IP ranges can be found here, see
`list of ips <https://confluence.atlassian.com/bitbucket/what-are-the-bitbucket-cloud-ip-addresses-i-should-use-to-configure-my-corporate-firewall-343343385.html>`_ 

Please see `webhook docs <https://support.atlassian.com/bitbucket-cloud/docs/manage-webhooks/>`_
for further information regarding Bitbucket Clouds webhooks.

Connection Configuration
------------------------

The supported options in ``zuul.conf`` connections are:

.. attr:: <bitbucketcloud connection>

   .. attr:: driver
      :required:

      .. value:: bitbucketcloud

         The connection must set ``driver=bitbucketcloud`` for Bitbucket Cloud
         connections.

   .. attr:: user
      :required:

      The Bitbucket Cloud username

   .. attr:: password
      :required:

      Required app password for connecting to the Bitbucket Cloud api.
      This is the app password created when setting up the Bitbucketcloud user
      account to interact with Zuul.

   .. attr:: sshkey
      :default: ~/.ssh/id_rsa

      Path to SSH key to use when cloning Bitbucket Cloud repositories, this
      path should point to the private key configured when creating SSH keys
      for the Bitbucket Cloud user. This will fall back to the Zuul users
      private key settings if not defined.

Trigger Configuration
---------------------
Bitbucket Cloud webhook events can be configured as triggers.

A connection name with the Bitbucket Cloud driver can take multiple events with
the following options.

.. attr:: pipeline.trigger.<bitbucketcloud source>

   The dictionary passed to the Bitbucket Cloud pipeline ``trigger`` attribute
   supports the following attributes:

   .. attr:: event
      :required:

      The event from Bitbucket Cloud. Supported events are:

      .. value:: bc_pull_request

      .. value:: bc_push

   .. attr:: action

      A :value:`pipeline.trigger.<bitbucketcloud source>.event.bc_pull_request`
      event will have associated action(s) to trigger from. The
      supported actions are:

      .. value:: created

         Pull request created.

      .. value:: declined

         Pull request declined.

      .. value:: comment

         Comment added to pull request.

   .. attr:: branch

      The branch associated with the event. Example: ``master``.  This
      field is treated as a regular expression, and multiple branches
      may be listed. Used for ``bc_pull_request`` events.

   .. attr:: comment

      This is only used for ``bc_pull_request`` ``comment`` actions.  It
      accepts a list of regexes that are searched for in the comment
      string. If any of these regexes matches a portion of the comment
      string the trigger is matched.  ``comment: retrigger`` will
      match when comments containing 'retrigger' somewhere in the
      comment text are added to a pull request.

   .. attr:: ref

      This is only used for ``bc_push`` events. This field is treated as
      a regular expression and multiple refs may be listed. Bitbucket Cloud
      always sends full ref name, eg. ``refs/tags/bar`` and this
      string is matched against the regular expression.

Reporter Configuration
----------------------
Zuul reports back to Bitbucket Cloud via the v2 Bitbucket Cloud API.
Available reports include a PR comment containing the build results, a commit
build status on start, success and failure and the ability to add a review on
a PR or decline a PR. Status name, description, and context is taken from the
pipeline.

.. attr:: pipeline.<reporter>.<bitbucketcloud source>

   To report to Bitbucket Cloud, the dictionaries passed to any of the pipeline
   :ref:`reporter<reporters>` attributes support the following
   attributes:

   .. attr:: status
      :type: str
      :default: None

      Report status via the Bitbucket Cloud `status API
      <https://developer.atlassian.com/bitbucket/api/2/reference/resource/repositories/%7Bworkspace%7D/%7Brepo_slug%7D/commit/%7Bnode%7D/statuses/build/%7Bkey%7D>`__.  Set to one of

      * ``INPROGRESS``
      * ``SUCCESSFUL``
      * ``FAILED``
      * ``STOPPED``

   .. attr:: status-url
      :default: link to the build status page
      :type: string

      URL to set in the Bitbucket Cloud build status.

      Defaults to a link to the build status or results page.  This
      should probably be left blank unless there is a specific reason
      to override it.

   .. attr:: comment
      :default: true

      Boolean value that determines if the reporter should add a
      comment to the pipeline status to the Bitbucket Cloud pull request. Only
      used for Pull Request based items.

   .. attr:: review

      One of `approve`, `unapprove`, or `decline` that causes the
      reporter to submit a review with the specified status on Pull Request
      based items. Has no effect on other items. In Bitbucket Cloud an
      unapprove action simply removes an approval. A decline closes the
      Pull request.


Reference pipelines
...................

Here is an example of standard pipelines you may want to define:

.. literalinclude:: /examples/pipelines/bitbucketcloud-reference-pipelines.yaml
   :language: yaml
