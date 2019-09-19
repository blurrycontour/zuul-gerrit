Zuul
====

Zuul is a project gating system.

The latest documentation for Zuul v3 is published at:
https://zuul-ci.org/docs/zuul/

If you are looking for the Edge routing service named Zuul that is
related to Netflix, it can be found here:
https://github.com/Netflix/zuul

If you are looking for the Javascript testing tool named Zuul, it
can be found here:
https://github.com/defunctzombie/zuul

What does Zuul do?
------------------

Zuul manages your continuous integration (CI) pipeline so that you
never again merge broken code.

It fully automates running tests defined by projects and guarantees
that changes have always passed before being committed.

Getting Help
------------

There are two Zuul-related mailing lists:

`zuul-announce <http://lists.zuul-ci.org/cgi-bin/mailman/listinfo/zuul-announce>`_
  A low-traffic announcement-only list to which every Zuul operator or
  power-user should subscribe.

`zuul-discuss <http://lists.zuul-ci.org/cgi-bin/mailman/listinfo/zuul-discuss>`_
  General discussion about Zuul, including questions about how to use
  it, and future development.

You will also find Zuul developers in the `#zuul` channel on Freenode
IRC.

Contributing
------------

To browse the latest code, see: https://opendev.org/zuul/zuul
To clone the latest code, use `git clone https://opendev.org/zuul/zuul`

Bugs are handled at: https://storyboard.openstack.org/#!/project/zuul/zuul

Suspected security vulnerabilities are most appreciated if first
reported privately following any of the supported mechanisms
described at https://zuul-ci.org/docs/zuul/user/vulnerabilities.html

Code reviews are handled by gerrit at https://review.opendev.org

After creating a Gerrit account, use `git review` to submit patches.
Example::

    # Do your commits
    $ git review
    # Enter your username if prompted

Join `#zuul` on Freenode to discuss development or usage.

License
-------

Zuul is free software.  Most of Zuul is licensed under the Apache
License, version 2.0.  Some parts of Zuul are licensed under the
General Public License, version 3.0.  Please see the license headers
at the tops of individual source files.

Python Version Support
----------------------

Zuul requires Python 3. It does not support Python 2.

Since Zuul uses Ansible to drive CI jobs, Zuul can run tests anywhere
Ansible can, including Python 2 environments.

High-level overview
-------------------

To understand the "Zen of Zuul" it is useful to follow a path from
individual jobs, through how jobs run to finally how Zuul decides what
to run and when.

CI Jobs
~~~~~~~

The first part of the story starts with the general idea of concept of
automatically running CI jobs when a change is proposed to a project.
In Gerrit terms a change is called a "review", in GitHub terms it is a
"pull request".  In modern projects there are usually many more unit
and functional tests in code than are practical for a developer to run
by themselves.  A subset is often run locally during development
covering the feature or bug being worked on, but larger tests
integrating the change across the entire code-base can be difficult
for each individual developer to setup and run consistently.  Who has
not made a "small" change that turned out to have unexpected
side-effects!

It is logical to move extensive per-change testing into an automated,
cloud-based environment.  Tests can run autonomously at massively
parallel scale while the developer moves on to other tasks.  Zuul
schedules, runs and manages the results of these jobs for you.  It
monitors projects for incoming changes and runs pre-configured testing
against them, captures relevant logs and debugging info and reports
back.

Any non-trivial code-base requires a considerable amount of setup even
before testing can be done.  You need various packages installed,
databases configured, networking setup or container environments
configured.  As a bonus, wouldn't it be great if your CI jobs set
themselves up using the same deployment methods you use in production,
so testing wasn't a special case?

One of the most popular ways to deploy complex (and not so complex)
software is `Ansible <https://www.ansible.com>>`__, which provides a
complete environment for software provisioning, configuration
management and application deployment.  For those with no prior
exposure to Ansible, it is in essence a tool to run commands on a
remote host.  A "playbook" is a series of commands to run; think of a
structured shell-script.  A "role" is analogous to a function that
encapsulates some common task.  Operators have long since realised
that bespoke random scripts can only go so far in orchestrating the
deployment of modern, complex systems, and tools like Ansible are
purpose built for the task.

Thus a "job" in Zuul means running Ansible playbooks against a remote
host.  The advantages of this are manifest when you start to dig into
the details.  To start simply, your Ansible job playbook could consist
of nothing but calling an existing shell-script and returning if it
passed or failed.  But quickly you realise the things the script are
likely doing are much better handled by Ansible itself.  Maybe you add
a user for testing using calls to "adduser" or "useradd" -- who can
remember.  Ansible has inbuilt roles to do that.  Then you install
some packages, making calls to "apt-get" or "dnf".  Ansible has
generic package installation routines to cover that.  Maybe you setup
a config file, using sed and awk calls to modify some parts.  Ansible
has a complete Jinja2 based template system to make this simple.  As
your complexity grows, you will start to realise that Ansible is
taking away the pain of ad-hoc scripts and your jobs are consisting of
well-tested, portable and compontentised building blocks.

If you use Ansible in production, the components you are using in the
testing environment can work exactly the same on live servers.  This
is the DevOps "Holy Grail" of infrastructure-as-code.  There are no
Zuul-specific custom configuration files or niche languages to come to
terms with; if you're familiar with basic Ansible concepts everything
is natural, and if you're not, any time invested means you are
acquiring broadly applicable Ansible skills.

Jobs benefit from the Ansible ecosystem providing you with a huge
array of common components.  Zuul itself comes with a `constantly
growing collection of roles
<https://opendev.org/zuul/zuul-jobs/src/branch/master/roles>`__ to
make the complex seem trivial.  Perhaps your job has two hosts to use
during testing, and need to configure the firewalls and ssh
authorisation between them -- there's roles for that.  Perhaps you
want to trigger `readthedocs <https://readthedocs.org>`__ to update
your documentation when a change is merged -- there's a role for that!
Perhaps you want your host setup with docker, nodejs, yarn or npm (all
things that can be surprisingly tricky) -- there's roles for that!
Roles for building documentation, uploading releases to PyPi and
related environments and interacting with container environments are
all provided -- and you are welcome to contribute more!  When your job
is done, it is only useful if you can see what it did.  Zuul comes
preconfigured with roles to collect and store logs, and interfaces to
show job results.  You can copy logs to a central file-server, upload
them to object storage or write your own roles to send them wherever
you want.

As your jobs grow, you will greatly benefit from Zuul's "implement
once and share" approach throughout the design.  Zuul jobs are
hierarchical; a child job can inherit from a parent.  That means, for
example, if you have a custom log collection role that runs after all
testing, you can put that in your site's "base" job.  Every other job
you write can inherit from that -- essentially it doesn't have to care
about log collection.  As jobs expand this becomes extremely powerful;
you may define a parent job to run ``tox`` and then child jobs can
simply set a variable to decide what version of Python to run with.

Much more is possible.  For example, Zuul keeps a private key for each
project it knows about, and publishes the public portion.  This means
that you can encrypt a secret value, say an API key or SSH private key
and keep it publicly in your repository.  When Zuul runs your job, it
can decrypt the secret and it can be used to automate authenticated
tasks.

But when it comes down to it, if all you want to do is run that shell
script, it does that just fine too.

Where do jobs run
~~~~~~~~~~~~~~~~~

Now you know that a Zuul job is, at a high level, arbitrary Ansible
playbooks that run against a remote host when changes are proposed or
updated.  But how and where does Zuul run these jobs?

Zuul runs with it's companion system `nodepool
<https://zuul-ci.org/docs/nodepool/>`__ for allocating resources to
run jobs.  The node types are defined by administrators and jobs
request from those predefined types.  Usually nodes are named for the
distribution, and/or size of the instance and other similar
parameters.  Nodepool has "drivers" to talk to a range of resource
providers like OpenStack, Kubernetes, Openshift and AWS.

Nodepool manages the life-cycle of the testing resources.  With
OpenStack, for example, it will manage the building and uploading of
the images to the cloud, starting the VM, setting up basic networking
(such as floating IP's), passing it over to Zuul for use and its
eventual removal.  It is aware of the cloud limits and makes smart
scheduling decisions about how to provide resources (e.g. I'm needing
a lot of this type of node, I'll pre-emptively start some; or we're
over capacity, I need to remove these unused nodes I started that
aren't being allocated).

From Zuul's view, it simply asks for nodes and, eventually, gets them.
If you enjoy excess capacity, likely instantly.  If not, nodes are
allocated as nodepool manages to balance out the incoming requests.

Zuul then starts Ansible and runs the job playbooks against these
testing nodes.  Zuul does this via it's "executor"; a sandboxed
environment that Ansible runs within.  Each job gets its own sandbox
environment; executor hosts can scale horizontally and as you scale up
the number of concurrent jobs you can add more hosts to handle more
executor processes.

When the job finishes, Zuul takes note of the final status for
reporting and releases the node for nodepool to reclaim.

Managing changes
~~~~~~~~~~~~~~~~

Submit a change, run some CI jobs, report back.  That's a good start
for a CI system, but when you start to examine modern high-volume,
multi-hundred developer, multi-hundred project workflows you start to
see a range of traps that Zuul completely insulates you from.

Never again should we hear "it worked for me!".  You can have 100%
test coverage of your code; but if the tests did not run it's all for
nothing.  A developer submits a change, tests run, pass and it now
waits for peer review.  In the mean time, 3 other things are committed
to the branch.  All too often, some days later we see this original
change has passed all tests and commit it.  Just because those other 3
changes didn't create a merge conflict (i.e. directly touch the same
code as being committed) does *not* mean it is safe to merge!  Maybe
the change obsoletes some API that the prior changes are now using.
The only way to really be safe is to run the testing again, against
the current top-of-tree.

It quickly becomes impractical for developers to manage this workflow
manually.  You have to implement locks where you ensure others don't
commit while you're testing.  People forget and commit anyway.  One
person is fixing while another is reverting and things get even worse.
Experience has proven the *only* practical way to manage a
multi-developer, CI-based workflow is to have tools test and merge
code safely for you.  This is a shift in thinking, but a very valuable
one.

People don't commit code any more.  People give the systems
*permission* to commit code.  In Gerrit, this might be a "workflow"
tag added to the review.  In GitHub this can be a comment or tag.  In
both cases you use the inbuilt authentication tools of your code
review tools to say who can add the flags that mark a change as "good
to commit".

At that point, you want your CI system to pick up the change, base it
on the current state of the code, *run the testing again*, and, if it
passes, then commit.  A first solution here would be to implement the
manual lock scenario above.  Take a top-of-tree lock, run all testing
again and commit; move on to the next change.  You will quickly find
that this does not scale, especially if tests might take in the range
of hours.

To optimise this, we can speculate that changes ahead of us *will*
pass, and run our testing including those changes.  To say this
another way, if change A is currently testing for merge, and change B
is approved for merge, it is valid for change B to first apply change
A, then itself (change B) and test.  This reflects the future state of
the tree at the time B will merge.

If A and B pass (as is common), they can be committed and we saved
considerable time by testing them in parallel.  If change A fails,
then change B should automatically re-test itself against the head of
the branch and have a chance to commit.  If change B fails while A is
running, or after A has merged, then clearly it conflicts with change
A and should not be merged.  Zuul manages all these complex
interactions to ensure that all changes are tested correctly but with
as much parallelism as possible.

Zuul's operation encourages developers to create better focused,
encapsulated changes by handling dependencies wisely.  If you submit a
"stack" of changes; three separate commits building on each other, for
example, Zuul ensures that each is tested in order.  What does this
mean practically?

When you write your test, you install your code from the checkout Zuul
has done for you in a known local source directory.  So, for example,
a job conceptually might be as simple as ``cd
/home/zuul/src/opendev.org/project/tree && tox``.  Zuul has sorted out
all the dependencies ahead of you and that source tree represents the
state you should be testing against.  But it gets even better!  You
can trivially do cross-project testing.  Say you depend on another
Python project; you can configure your jobs to *also* check-out this
project alongside your own code.  What this means is, in your job,
instead of doing say ``pip install project`` and getting the code from
PyPi, you would do ``pip install
/home/zuul/src/github.com/foo/project`` to use the source-tree Zuul
has checked out.  If you wish to test against another, uncommitted
change in ``project`` too, simply add ``Depends-On:
https://github.com/foo/project/pull-request`` that points to the pull
request for the other project you wish to test against.  Now Zuul will
automatically apply that change for the on-disk code tree and you will
test against it.  If your change ``Depends-On:`` an uncommitted
change, Zuul will know not allow it to merge either!

Zuul implements it's change management via completely configurable
*pipelines*.  It watches the changes (or pull requests) coming in for
projects and matches the current state of that change against pre-set
rules that will decide which pipeline queue the change should be
placed into.  Projects configure the jobs they want to run in each
pipeline.  Pipelines can be configured to your workflow, but common
patterns emerge.

For example, it is common to configure a *check* pipeline that
captures new changes that are uploaded but not yet authorized for
merge.  Jobs in this pipeline run against the current top-of-tree;
Zuul reports back with the results (usually via a comment, although
some code review systems have special reporting mechanisms for
automated testing).  Errors here are the first flag for a developer if
something is wrong with their change.

When Zuul sees a change is updated with approval tags, it can go into
a *gate* pipeline that is setup to ensure strict ordering of commits
as described above.  Once the change passes in this pipeline, it is
merged in order; note Zuul does not merge the change directly, but
signals to the code review system (via API or similar) the change
should be merged.  Usually projects configure the same jobs to run in
the gate pipeline as the check pipeline, although they do not have to.

Zuul can be watching to see when changes are merged, and then put that
merged change in a *post* pipeline where jobs might do things like
release code-tarballs.  You might want a *periodic* pipeline that runs
against the top-of-tree change at a preconfigured time (e.g. for a
daily documentation release, or a long-running test not appropriate
for every change).  Pipelines are all in a sense arbitrary, but
*check*, *gate* and *post* are certainly the most common tropes.

Project gating
~~~~~~~~~~~~~~

All of the above works together to build a concept simply referred to
as *project gating*.  This refers to the idea that you use the CI
tools to only let proven good changes through the metaphorical gate,
and gain the multitude of benefits from a consistently stable
code-base.

The workflows enabled by Zuul mean anything from a handful to hundreds
of developers can work together effectively across a handful to
hundreds of projects simultaneously.
