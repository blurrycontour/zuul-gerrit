What does Zuul do?
------------------

Zuul manages your continuous integration (CI) pipeline so that you
never again merge broken code.

It fully automates running tests defined by projects and guarantees
that changes have always passed testing before being merged.

High-level overview
-------------------

To understand the "Zen of Zuul" it is useful to follow a path through
understanding continuous integration, look at how Zuul defines and
runs testing jobs to finally how Zuul decides what and when to run.

It is important to understand a few key concepts before this journey.

Zuul does *not* store your code.  Tools such as Gerrit, GitHub or
GitLab hold your git trees, manage the comments and revisions of
changes, who has permissions to flag code for merge and ultimately,
the merge of that new code.  Zuul works *with* these tools to manage
your continuous integration and deployment workflows.

Humans do not *merge* code with the Zuul model.  Humans review the
code and give Zuul *permission* to merge code, which it then does in a
safe manner.

Continuous Integration
~~~~~~~~~~~~~~~~~~~~~~

To start right at the beginning; once two or more developers are
working on common code in parallel they have an integration problem.

If both simultaneously decide to change the same function there is now
a race for who will commit that change to the main repository; one
developer will "win" and one will inevitably have to fix their code to
the new state.  Conflict merges such as this are easy to detect
(though may not be so easy to solve!).  If one developer changes a
common function ``foo(int)`` to ``foo(float)`` and the other changes
it to ``foo(char)`` one will commit their change first, then when the
other tries to commit the tools will raise an error saying something
like "I should be changing a line ``foo(int)`` to ``foo(char)`` but it
appears to be ``foo(float)``.  It is then up to the developer to
figure out an appropriate solution, which probably requires discussion
and refactoring.

However, there are much more difficult to uncover bugs when
integrating changes to complex software.  If one developer changes
``foo(int)`` to return ``1`` instead of ``0`` , this will *not* be
detected as a merge conflict.  Presumably the developer fixed all
in-tree callers of ``foo()``; however, any outstanding changes calling
``foo()`` and expecting a return code of ``0`` will now be incorrect
and, if merged to the repository, will cause a breakage.  This type of
failure can only be uncovered by testing against the current state of
the repository; developers have an arsenal of unit testing, functional
testing and integration testing to uncover situations where their code
is not working as expected.

The faster integration problems are found, the better.  Developers
with a few grey hairs may remember software teams that worked for
months in silos, only integrating to the common shared repository on
specific (dreaded) "merge days" when all work had to stop to fix the
inevitable breakage.

It is not that developers didn't understand the inevitable
consequences of merging their changes, but the tools and processes for
managing distributed development of the time did not allow for
effective high velocity distributed development.  As tools such as
CVS, Subversion and git grew, managing and merging code became a more
tractable problem.  Cadences for merge shrunk from months to weeks,
days, or hours (Wikipedia defines continuous integration as "... a
development practice where developers integrate code into a shared
repository frequently, preferably several times a day".).

Shrinking the merge window reduces the possibility for conflicts.
However, if there are *any* changes committed to the shared repository
you have not tested against, there is always the possibility something
the new code relies on has changed and thus there is an opportunity
for breakage.

However, there is an atomic end to reducing the merge window; if you
reduce it not to hours, minutes or even seconds but by merging
individual tested changes *sequentially* you can completely avoid
these types of integration problems.

If *every* change is tested against the current state of the
repository before it is merged, there is *no* window for integration
problems to manifest.  In this situation *you can not merge broken
code*.  This is the holy-grail of continuous integration.

Many readers will at this point be saying "but I have hundreds of
developers, working on a multitude of code repositories; I can not
possibly have them all stand in single queue waiting for the person in
front of them to run tests and commit their code".

This is *exactly* what Zuul will manage for you.  By speculatively
testing changes it can merge code in parallel *and* ensure that broken
changes never merge.  It almost sounds too good to be true, but Zuul
was forged by lessons learnt merging hundreds of thousands of changes
in the OpenStack project with thousands of distributed developers.

Automated Testing
~~~~~~~~~~~~~~~~~

Code is safe to merge when it has passed testing.  Ultimately, the
safety of merging is only as good as the testing done on the code --
"if it's not tested it's broken".

So on one hand we want as much and extensive testing as possible.
However, in modern projects there are usually many more tests code
than are practical for a developer to run by themselves.  A subset is
often run locally during development covering the feature or bug being
worked on, but larger tests integrating the change across the entire
code-base can be difficult for each individual developer to setup and
run consistently or take an impractical amount of time to run.  Who
has not made a "small" change that turned out to have unexpected
side-effects!

It is a logical step to move extensive per-change testing away from an
individual developer's environment into an automated, cloud-based
environment.  Tests can run autonomously at massively parallel scale
while the developer moves on to other tasks.

Zuul schedules, runs, monitors, collects and presents the results of
testing for developers.  Exactly how this is done is explored below.

While testing is a requirement before merging code, you also want
these same tests to run before human review.  Developer time is
expensive, and there is no point having people review code that
contains errors the automated test-suite has picked up.  It is better
for the author to fix these merge-blocking mistakes before asking
their peers for detailed code review.

Zuul manages the entire life-cycle of a change; it monitors projects
for incoming changes and runs pre-configured testing against them,
captures relevant logs and debugging info and reports back so that
reviewers know the code has passed testing.  Once approved Zuul will
handle re-testing, merge and any post-merge tasks required.

Running tests
~~~~~~~~~~~~~

To recap; Zuul is listening for incoming code changes from your change
management tool and will automatically execute your tests against the
proposed change.  But what exactly does it mean for Zuul to execute
tests?  How is it done?

Firstly, projects define "jobs", usually in their own source tree.  A
``.zuul.yaml`` configuration file defines a series of jobs.  Each job
defines the tasks to run, the resources it requires to run on and
other `well documented
<https://zuul-ci.org/docs/zuul/reference/jobs.html>`__ options
(e.g. filters that might run documentation jobs only when files in
``docs/`` are touched).

Any non-trivial code-base requires a considerable amount of setup even
before testing can be done.  For example you need various packages
installed, databases initalised, configuration files written,
networking setup or container environments configured.

Often tools to automatically run tests will use a bespoke
domain-specific language (DSL) or a custom configuration file format
to define their actions.  With this model, too often testing
environments are setup in an ad-hoc manner; they do not remotely
reflect the production environment and introduce a large surface area
of problems that only happen when you deploy your code (bad!).

Zuul provides a bridge for this gap between testing and production by
leveraging the power of `Ansible <https://www.ansible.com>`__ in its
jobs.  So when we say Zuul runs a job, this largely means that Zuul
runs an Ansible against the hosts defined in the job.

For those with no prior exposure to Ansible, it is in essence a tool
to run commands on a remote host.  Operators have long since realised
that bespoke random scripts can only go so far in orchestrating the
deployment of modern, complex systems and tools like Ansible are
purpose built for the task.  A "playbook" is a series of commands to
run; think of a structured shell-script.  A "role" is analogous to a
function call that encapsulates some common task.  Roles are designed
to be self-encapsulated, idempotent and shared.

The power of this approach is that a job can grow from Ansible being
used to call an existing shell script and get out of the way, to
evolve into a fully orchestrated and generic playbook used for
continuous deployment in production.

The advantages of this are manifest when you start to dig into the
details.  Ansible provides a ready-made environment for software
provisioning, configuration management and application deployment.
Most importantly, Zuul does not have a DSL or custom configuration
file to define tasks.

To illustrate a common situation that plays out building jobs:

* To start simply, a test playbook consists of nothing but calling an
  existing shell-script and returning if it passed or failed.
* Soon it becomes clear some of the things the script are doing are
  much better handled by Ansible itself.  Maybe a user is added for
  testing using calls to ``adduser`` or ``useradd`` -- who can
  remember?  Ansible has inbuilt roles to do common tasks like that.
* You wish to install some common packages, but want the job to work
  on both CentOS and Ubuntu.  Ansible has generic package installation
  routines to cover that so you don't have to worry about platform
  detection, ``yum`` v ``dnf``, etc.
* You need to setup a config file, currently done with a series of
  complex ``sed`` and ``awk`` calls.  This is easily pulled out as
  Ansible has a complete Jinja2 based template system for writing
  files.
* This same setup needs to happen in production, and now you have most
  of it encapsulated in reusable Ansible playbooks and roles.

Using Ansible you can build jobs that consist of of well-tested,
portable and compontentised building blocks; but retain the ability to
just call out to an ad-hoc or existing scripts if you need it.  If
you're familiar with basic Ansible concepts everything is natural, and
if you're not, any time invested means you are acquiring broadly
applicable Ansible skills.

Test jobs benefit from the Ansible ecosystem providing you with a huge
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
all provided -- and you are welcome to contribute more!

When your test is done, it is only useful if you can see what it did.
Zuul comes preconfigured with roles to collect and store logs to
common cloud storage providers, and interfaces to show job results.
You can copy logs to a central file-server, upload them to object
storage or write your own roles to send them to any desired
destination.

As your tests grow, you will greatly benefit from Zuul's "implement
once and share" approach throughout the design which lets you stick to
the well established DRY principles.  Zuul jobs are hierarchical; a
child job can inherit from a parent.  That means, for example, if you
have a custom log collection role that runs after all testing, you can
put that in your site's "base" job.  Every other job you write can
inherit from that -- essentially it doesn't have to care about log
collection.  As jobs expand this becomes extremely powerful; you may
define a parent job to run ``tox`` and then child jobs can simply set
a variable to decide what version of Python to run with.

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
parameters.  Nodepool implements "drivers" to talk to a range of
resource providers like OpenStack, Kubernetes, Openshift and AWS.

Nodepool manages the life-cycle of the testing resources.  With
OpenStack, for example, it will manage the building and uploading of
the images to the cloud, starting the VM, setting up basic networking
and passing the details over to Zuul to run the jobs and the eventual
removal when the job finishes.  It is aware of the cloud limits and
makes smart scheduling decisions about how to provide resources
(e.g. pre-emptively starting nodes when it can see their is increasing
demand for them, or removing unused nodes when over capacity).

From Zuul's view, it simply asks for nodes and, eventually, gets them.
If you enjoy excess capacity, likely instantly.  If not, nodes are
allocated as nodepool manages to balance out the incoming requests.

Zuul then starts Ansible and runs the job playbooks against these
testing nodes.  Zuul does this using it's "executor"; a sandboxed
environment that Ansible runs within.  Each job gets its own sandbox
environment; executor hosts can scale horizontally and as you scale up
the number of concurrent jobs you can add more hosts to handle more
executor processes.

When the job finishes, Zuul takes note of the final status for
reporting and releases the node for nodepool to reclaim.

Managing changes
~~~~~~~~~~~~~~~~

As discussed above, Zuul handles the sequential merging of changes to
ensure correctness by ensuring there is never a merge window where
untested code is committed.  You can have 100% test coverage of your
code; but if the tests did not run before the code was merged it is
ultimately futile.

It is impractical for developers to manage this work-flow manually.
There has to be a lock where you ensure others don't commit while you
are testing.  This does not scale.

We mentioned at the start that people do not merge code any more --
rather people give Zuul *permission* to try and merge the code.  In
Gerrit, this might be a "workflow" tag added to the review.  In GitHub
this can be a comment or tag.  In both cases you use the inbuilt
authentication tools of your code review tools to say who can add the
flags that mark a change as "good to merge".

At that point, you want your CI system to pick up the change, base it
on the current state of the code, *run the testing again*, and, if it
passes, merge.

Merging to the current tree and testing eliminates one class of
problems; for example where a change was proposed an initially tested
several days ago, and is then accepted for merge and needs to be
re-tested with the current state of the tree.  However, unless you
lock out any other changes from merging while you test, you risk
merging into an untested state.  This is where many CI systems that
are not designed for extremely high volume of both changes and tests
are lacking.

A first solution would be to implement the manual lock scenario above.
Take a top-of-tree lock, run all testing again and merge; move on to
the next change.  You will quickly find that this does not scale,
especially if you have extensive tests that might take in the range of
hours.

To optimise this, we can speculate that changes ahead of us *will*
pass, and run our testing including those changes.  To say this
another way, if change A is currently testing for merge, and change B
is approved for merge, it is valid for change B to first apply change
A, then itself (change B) and test.  This reflects the probable future
state of the tree at the time B will merge.

If A and B pass (as is common), they can be committed and we saved
considerable time by testing them in parallel.  If change A fails,
then change B should automatically re-test itself against the head of
the branch and have a chance to commit.  If change B fails while A is
running, or after A has merged, then clearly it conflicts with change
A and change B should not be merged.  Zuul manages all these complex
interactions to ensure that all changes are tested correctly but with
as much parallelism as possible.

Zuul's operation encourages developers to create better focused,
encapsulated changes by handling dependencies wisely.  If you submit a
"stack" of changes; multiple small and logically encapsulated separate
commits building on each other, for example, Zuul ensures that each is
tested in order.

What does this mean practically?

When you write your test, you install your code from the checkout Zuul
has done for you in a known local source directory.  So, for example,
a job conceptually might be as simple as ``cd
/home/zuul/src/opendev.org/project/tree && tox``.  Zuul has sorted out
all the dependencies ahead of you and that source tree represents the
state you should be testing against.

But it gets even better!

You can trivially do cross-project testing.  Say you depend on another
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

Pipelines
~~~~~~~~~

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

You might want a *periodic* pipeline that runs against the top-of-tree
change at a preconfigured time (e.g. for a daily documentation
release, or a long-running test not appropriate for every change).
Pipelines are all in a sense arbitrary, but *check*, *gate* and
*periodic* are certainly the most common tropes.

Continuous Deployment
~~~~~~~~~~~~~~~~~~~~~

Zuul can be watching to see when changes are merged, and then put that
merged change in a *post* pipeline.  This is a continuous-deployment
scenario; the change has been merged and the tree can now be released
or rolled out into production.

For example, you may have jobs that release code tarballs, upload code
to repositories such as PyPi or trigger API end-points that initiate
further action (this can also be in response to more specific actions,
such as tagging a release, etc.).

You could just as easily have Zuul configured to deploy merged code to
live production servers.  This is where infrastructure-as-code becomes
a reality -- when the same Ansible roles that run during the *gate*
tests are used to deploy production code you can be assured of no
nasty surprises, because the code has been tested!


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
