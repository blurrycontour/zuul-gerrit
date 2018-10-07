Zuul is not like other CI or CD systems.  It is a project gating
system designed to assist developers in taking a change from proposal
through deployment.  Zuul can support any number of workflow processes
and systems, but to help you get started with Zuul, this tutorial will
walk through setting up a basic gating configuration which protects
projects from merging broken code.

This tutorial is entirely self-contained and may safely be run on a
workstation.  The only requirements are a network connection and the
ability to run Docker containers.  For code review, it provides an
instance of Gerrit, though the concepts you will learn apply equally
to GitHub.  Even if you don't ultimately intend to use Gerrit, you are
encouraged to follow this tutorial to learn how to set up Zuul and
then consult further documentation to configure your Zuul to interact
with GitHub.

Before you start, ensure that some needed packages are installed.

.. code-block:: bash

   # Debian / Ubuntu:

   apt-get install docker-compose git git-review

   # Red Hat / Fedora / SUSE:

   yum install docker-compose git git-review

Clone the Zuul repository:

.. code-block:: bash

   git clone https://git.zuul-ci.org/zuul

Then cd into the directory containing this document, and run
docker-compose in order to start Zuul, Nodepool and Gerrit.

.. code-block:: bash

   cd zuul/doc/source/examples
   docker-compose up

All of the services will be started with debug-level logging sent to
the standard output of the terminal where docker-compose is running.
You will see a considerable amount of information scroll by, including
some errors.  Zuul will immediately attempt to connect to Gerrit and
begin processing, even before Gerrit has fully initialized.  The
docker composition includes scripts to configure Gerrit and create an
account for Zuul.  Once this has all completed, the system should
automatically connect, stabilize and become idle.  When this is
complete, you will have the following services running:

* Zookeeper
* Gerrit
* Nodepool Launcher
* Zuul Scheduler
* Zuul Web Server
* Zuul Executor
* Apache HTTPD

And a long-running static test node used by Nodepool and Zuul upon
which to run tests.

The Zuul scheduler is configured to connect to Gerrit via a connection
named `gerrit`.  Zuul can interact with as many systems as necessary,
each such connection is assigned a name for use in the Zuul
configuration.

Zuul is a multi-tenant application, so that differing needs of
independent work-groups can be supported from one system.  This
example configures a single tenant named `example-tenant`.  Assigned
to this tenant are three projects: `zuul-config`, `test1` and `test2`.
These have already been created in Gerrit and are ready for us to
begin using.

Add Your Gerrit Account
=======================

Before you can interact with Gerrit, you will need to create an
account.  The initialization script has already created an account for
Zuul, but has left the task of creating your own account to you so
that you can provide your own SSH key.  You may safely use any
existing SSH key on your workstation, or you may create a new one by
running `ssh-keygen`.

Gerrit is configured in a development mode where passwords are not
required in the web interface and you may become any user in the
system at any time.

To create your Gerrit account, visit http://localhost:8080 in your
browser and click `Become` then click `New Account` under *Register*.

Enter your full name and click `Save Changes`, enter the username you
use to log into your workstation in the `Username` field and click
`Select Username`, then copy and paste the contents of
`~/.ssh/id_rsa.pub` into the SSH key field and click `Add`.  Click
`Continue`.

At this point you have created and logged into your personal account
in Gerrit and are ready to begin configuring Zuul.

Configure Zuul Pipelines
========================

Zuul recognizes two types of projects: :term:`config
projects<config-project>` and :term:`untrusted
projects<untrusted-project>`.  An *untrusted project* is a normal
project from Zuul's point of view.  In a gating system, it contains
the software under development and/or most of the job content that
Zuul will run.  A *config project* is a special project that contains
the Zuul's configuration.  Because it has access to normally
restricted features in Zuul, changes to this repository are not
dynamically evaluated by Zuul.  The security and functionality of the
rest of the system depends on this repository, so it is best to limit
what is contained within it to the minimum, and ensure thorough code
review practices when changes are made.

Zuul has no built-in workflow definitions, so in order for it to do
anything, you will need to begin by making changes to a *config
project*.  The initialization script has already created a project
named `zuul-config` which you should now clone onto your workstation:

.. code-block:: bash

  git clone http://localhost:8080/zuul-config

You will find that this repository is empty.  Zuul reads its
configuration from either a single file or a directory.  In a *Config
Project* with substantial Zuul configuration, you may find it easiest
to use the `zuul.d` directory for Zuul configuration.  Later, in
*Untrusted Projects* you will use a single file for in-repo
configuration.  Make the directory:

.. code-block:: bash

   cd zuul-config
   mkdir zuul.d

The first type of configuration items we need to add are the Pipelines
we intend to use.  In Zuul, a Pipeline represents a workflow action.
It is triggered by some action on a connection.  Projects are able to
attach jobs to run in that pipeline, and when they complete, the
results are reported along with actions which may trigger further
Pipelines.  In a gating system two pipelines are required:
:term:`check` and :term:`gate`.  In our system, `check` will be
triggered when a patch is uploaded to Gerrit, so that we are able to
immediately run tests and report whether the change works and is
therefore able to merge.  The `gate` pipeline is triggered when a code
reviewer approves the change in Gerrit.  It will run test jobs again
(in case other changes have merged since the change in question was
uploaded) and if these final tests pass, will automatically merge the
change.  To configure these pipelines, copy the following file into
`zuul.d/pipelines.yaml`:

.. literalinclude:: examples/zuul-config/zuul.d/pipelines.yaml
   :language: yaml

Once we have bootstrapped our initial Zuul configuration, we will want
to use the gating process on this repository too, so we need to attach
the `zuul-config` repository to the `check` and `gate` pipelines we
are about to create.  There are no jobs defined yet, so we must use
the internally defined `noop` job, which always returns success.
Later on we will be configuring some other projects, and while we will
be able to dynamically add jobs to their pipelines, those projects
must first be attached to the pipelines in order for that to work.  In
our system, we want all of the projects in Gerrit to participate in
the check and gate pipelines, so we can use a regular expression to
apply this to all projects.

To configure the `check` and `gate` pipelines for `zuul-config` to run
the `noop` job, and add all projects to those pipelines (with no
jobs), copy the following file into `zuul.d/projects.yaml`:

.. literalinclude:: examples/zuul-config/zuul.d/projects.yaml
   :language: yaml

Commit the changes and push them up for review:

.. code-block:: bash

   git add zuul.d
   git commit
   git review

Because Zuul is currently running with no configuration whatsoever, it
will ignore this change.  For this initial change which bootstraps the
entire system, we will need to bypass code review (hopefully for the
last time).  To do this, you need to switch to the Administrator
account in Gerrit.  Visit http://localhost:8080 in your browser,

click 'switch account'
click 'admin'
visit http://localhost:8080/#/c/zuul-config/+/1001/
click reply
vote +2 +2 +1 post
submit
click 'switch account'
click your username

set up base job
===============

add empty base job
add change to test1
job should succeed but no logs

add playbooks to zuul-config
create mode 100644 playbooks/base/post-ssh.yaml
create mode 100644 playbooks/base/pre.yaml
