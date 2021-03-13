.. _gate_your_first_patch:

Zuul Hands on - Your first gated patch with Zuul
------------------------------------------------

In this article, we will create a project and explain how to configure a basic
CI workflow in order to gate your first patch with Zuul.

The instructions and examples below are given for a :ref:`quick_start` setup.


Provision the test1 source code
,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

We can now clone **test1**:

.. code-block:: bash

  git clone http://localhost:8080/test1
  cd test1
  git review -s

You will be prompted for your username on Gerrit, use your account username.

If you went through others articles of the series and **test1** already exists,
reset the state to origin/master and remove existing files

.. code-block:: bash

  cd test1
  git fetch --all --prune
  git reset --hard origin/master
  rm -rf .zuul.yaml *

Let's add some basic code in **test1**; create the following **hello.py** file
in the repository:

.. literalinclude:: ../examples/test1-gate-first/hello.py
   :language: python

Configure a Zuul job for test1
..............................

We will now create a job and configure the **test1** project's Zuul pipelines,
so that this job is run at checking and gating times to ensure the quality of a
patch.

Zuul allows jobs and pipelines to be defined in an external repository (this is useful if you
have several repositories that share the same testing needs, for example setting up a
common testing environment), but also to be defined within a code repository itself.
This is the approach we're going to use here.

First, we define a job playbook in **test1**. To do so, create the
**playbook** directory then the file **playbooks/unittests.yaml**:

.. literalinclude:: ../examples/test1-gate-first/playbooks/unittests.yaml
   :language: yaml

Note that we are using the **zuul.project.src_dir** variable to set the task's working
directory to the repository's root. Zuul defines a fair amount of variables that
can be used when writing jobs; the full list and descriptions are available
:ref:`Job variables <user_jobs_job_variables>`

In the second step, we define the **unit-tests** Zuul job and attach it to the
project's Zuul pipelines. Zuul looks for a file named **.zuul.yaml** within the
repository; this file defines jobs and pipelines for this repository.

In **test1**, create the file **.zuul.yaml**:

.. literalinclude:: ../examples/test1-gate-first/zuul.yaml
   :language: yaml

Submit the change to Gerrit:

.. code-block:: bash

  git add -A
  git commit -m"Init test1 pipelines"
  git review

Note that this time, we don't push directly the change to the repository but we
go through the code review system. This is because Zuul automatically detects
changes to the configuration files within a patch on the repository, and evaluates
them speculatively. In other words, the jobs we added to the check pipeline will
be run to validate the patch, even though this configuration change hasn't been merged yet.

This lets you make sure that your changes to the CI do what you expect before applying
them globally, instead of potentially wrecking the CI for all contributors.

Gating made easy
................

With this rather simple patch, we tell Zuul to:

- run the **unit-tests** job in the **check** pipeline, ie whenever a new
  patch or a change to an existing patch is submitted to Gerrit.
- run the **unit-tests** job in the **gate** pipeline, ie right after a patch has
  been approved but before it is merged. This is to acknowledge any discrepancies
  between the state of the repository when the change was last tested and its
  current state (several patches might have landed in between, with possible
  interferences). We will dive into the details of the gate pipeline in a
  follow-up article.
- call the Gerrit API to merge the patch if the job execution in the **gate**
  pipeline succeeded.

The **unit-tests** job is simple, it tells Zuul to execute the Ansible
playbook **unittests.yaml**, which contains a single task, ie run python's
unittest module on the hello.py file.

The job can be kept simple because it "inherits" automatically from the default
base job which handles all of the grisly details like setting up the test environment
and exporting logs. The **base** job, rather than being inherited, more accurately
encapsulates the unit-tests job, by running a **pre** playbook before unit-tests,
and a **post** playbook after **unit-tests**, regardless of whether the latter
ended in success or failure.

Because we haven't specified an inventory (also called *nodeset*, due to Zuul's
multi-node capabilities), the **unit-tests** job will be run on the default nodeset
defined in the **base** job.

Now, check that Zuul has run the job in the check pipeline and has reported a
**+1** in the *Verified Label*, on the patch's Gerrit page.

.. image:: /images/gate-first-patch-verified.png
   :align: center

To access a given job's run's logs, simply click on the job name.

Use the Gerrit web interface to approve the
change and let Zuul run the gate job and merge the change.

You should soon see the gate job appear on the `Zuul status page <http://localhost:9000/zuul/t/example-tenant/status>`_.

.. image:: /images/gate-first-patch-zuul-gate-status.png
   :align: center

Clicking on the job's name brings you to the Zuul job console. The **unittests** playbook
should wait for 60 seconds before starting the **python3 -m unittests** command
so we should have time to witness the execution of the job in real time in the console.

.. image:: /images/gate-first-patch-zuul-gate-console.png
   :align: center

As soon as the **gate** job finishes successfully, Zuul merges the patch
in the **test1** repository.

If you reached that point, congratulations, you successfully configured
Zuul to gate patches on **test1** !

.. image:: /images/gate-first-patch-merged.png
   :align: center

Now, any new patch submitted to the **test1** repository will trigger automatically
this same CI workflow.

Exercises left to the reader
............................

* Send a new patch that fails to pass the check pipeline. Then fix it by amending it.
* Read the default **base job** in the config repository.

Next we will use Zuul's jobs library to take advantage of pre-defined Ansible roles to ease job creation.
