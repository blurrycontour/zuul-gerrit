:title: Gitea Driver

.. _gitea_driver:

Gitea
=====

The Gitea driver supports sources, triggers, and reporters.  It can
interact with site-local installations of Gitea.

Configure Gitea
---------------

Zuul interacts with projects hosted on Gitea by:

- receiving events via web-hooks
- performing actions via the API

web-hooks
^^^^^^^^^

Each project to be integrated with Zuul needs:

- "Web hook target URL" set to
  http://<zuul-web>/api/connection/<conn-name>/payload
- Web hook "Trigger On" set to "All Events"
- Same Webhook Secret

In Gitea it is possible to set webhooks on the repository, organization or
system level.

API
^^^

Gitea currently does not support restricting API token
permissions. Neither it supports bot accounts. Because of
that special care should be taken configuring Zuul.

It is strongly recommented to create separate user for
Zuul API access. This user should not have admin access
to any project it manages, since in this case it is
possible to accidentially bypass branch protection
policies. Instead it should have only write permission on
every project it manages. Branch protection rules can not
be enforced for accounts with Admin permissions.

The API token must be created in user "Settings" >
"Applications" > "Generate New Token".

When branch protections are used it is recommended to
ensure only Zuul user is whitelisted to perform the merge
("Branch protection" > "Enable Merge Whitelist").

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

      .. value:: gt_pull_request_review

      .. value:: gt_push

   .. attr:: action

      A :value:`pipeline.trigger.<gitea source>.event.gt_pull_request`
      event will have associated action(s) to trigger from. The
      supported actions are:

      .. value:: opened

         Pull request opened.

      .. value:: changed

         Pull request synchronized (new commit or body update).

      .. value:: closed

         Pull request closed.

      .. value:: reopened

         Pull request reopened.

      .. value:: comment

         Comment added to pull request.

      .. value:: reviewed

         Review added to pull request.

      .. value:: label_updated

         Pull request labels updated.

      .. value:: edited

         Pull request modified (title, body)

      A :value:`pipeline.trigger.<gitea
      source>.event.gt_pull_request_review` event will have associated
      action(s) to trigger from. The supported actions are:

      .. value:: submitted

         Pull request review added.

   .. attr:: comment

      This is only used for ``gt_pull_request`` and ``comment`` actions.  It
      accepts a list of regexes that are searched for in the comment
      string. If any of these regexes matches a portion of the comment
      string the trigger is matched.  ``comment: retrigger`` will
      match when comments containing 'retrigger' somewhere in the
      comment text are added to a pull request.

   .. attr:: ref

      This is only used for ``gt_push`` events. This
      field is treated as a regular expression and
      multiple refs may be listed, eg. ``refs/tags/bar``.
      Gitea reported reference is then matched against
      the regular expression.

   .. attr:: state

      This is only used for ``gt_pull_request_review`` events.  It
      accepts a list of strings each of which is matched to the review
      state, which can be one of ``approved``, ``comment`` or
      ``request_changes``.


Reporter Configuration
----------------------
Zuul reports back to Gitea via Gitea API. Available reports include a PR
comment containing the build results, a commit status on start, success and
failure. Status name, description, and context
is taken from the pipeline.

.. attr:: pipeline.<reporter>.<gitea source>

   To report to Gitea, the dictionaries passed to any of the pipeline
   :ref:`reporter<reporters>` attributes support the following
   attributes:

   .. attr:: status

      String value (``pending``, ``success``, ``failure``, ``error``,
      ``warning``) that the reporter should set as the commit status on
      Gitea.

   .. attr:: comment
      :default: true

      Boolean value that determines if the reporter should add a
      comment to the pipeline status to the Gitea Pull Request. Only
      used for Pull Request based items.

   .. attr:: merge
      :default: false

      Boolean value that determines if the reporter should merge the
      pull reqeust. Only used for Pull Request based items.

Requirements Configuration
--------------------------

As described in :attr:`pipeline.require` pipelines may specify that items
meet certain conditions in order to be enqueued into the pipeline. These
conditions vary according to the source of the project in question.

.. code-block:: yaml

   pipeline:
     require:
       gitea:
         open: true

This indicates that changes originating from the Gitea connection must be
in the *opened* state (not merged yet).

.. attr:: pipeline.require.<gitea source>

   The dictionary passed to the GitLab pipeline `require` attribute
   supports the following attributes:

   .. attr:: open

      A boolean value (``true`` or ``false``) that indicates whether
      the Merge Request must be open in order to be enqueued.

   .. attr:: merged

      A boolean value (``true`` or ``false``) that indicates whether
      the Merge Request must be merged or not in order to be enqueued.

   .. attr:: approved

      A boolean value (``true`` or ``false``) that indicates whether
      the Merge Request must be approved or not in order to be enqueued.

   .. attr:: labels

      A list of labels a Merge Request must have in order to be enqueued.

Reference pipelines configuration
---------------------------------

Branch protection rules
^^^^^^^^^^^^^^^^^^^^^^^

The rules prevent Pull requests to be merged on defined branches if they are
not met. For instance a branch might require that specific status are marked
as ``success`` before allowing the merge of the Pull request.

Zuul provides the attribute tenant.untrusted-projects.exclude-unprotected-branches.
This attribute is by default set to ``false`` but we recommend to set it to
``true`` for the whole tenant. By doing so Zuul will benefit from:

 - exluding in-repo development branches used to open Pull requests. This will
   prevent Zuul to fetch and read useless branches data to find Zuul
   configuration files.
 - reading protection rules configuration from the Gitea API for a given branch
   to define whether a Pull request must enter the gate pipeline. As of now
   Zuul only takes in account "Required approvals count" and "Enable Status Check".

With the use of the reference pipelines below, the Zuul project recommends to
set the minimum following settings:

 - attribute tenant.untrusted-projects.exclude-unprotected-branches to ``true``
   in the tenant (main.yaml) configuration file.
 - on each Gitea repository, activate the branch protections rules and
   configure the name of the protected branches. Furthermore set "Enable status
   checks" and check the status labels checkboxes (at least
   ```<tenant>/check```) that must be marked as success in order for Zuul to
   make the Pull request enter the gate pipeline to be merged.

Here is an example of standard pipelines you may want to define:

.. literalinclude:: /examples/pipelines/gitea-reference-pipelines.yaml
   :language: yaml
