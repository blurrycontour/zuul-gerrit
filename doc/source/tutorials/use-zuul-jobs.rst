Use the Zuul jobs library
-------------------------

In this article, we will:

- provision a python project with a test suite based on tox
- explain how to use the `zuul-jobs library <https://opendev.org/zuul/zuul-jobs>`_ in
  order to benefit from jobs maintained by the Zuul community.

Please run :ref:`quick-start` first to get a Zuul system up and running if
you don't already have one.


The Zuul Jobs Library
.....................

By design Zuul promotes reusability in its approach to jobs. In that spirit, a
public jobs library is available at https://opendev.org/zuul/zuul-jobs .

The library contains jobs that can be used directly as is, and more elementary
roles that can be included into your own playbooks.

As of now the **zuul-jobs** library covers mainly typical CI or
CD needs for Python and Javascript projects, for example:

- publishing a package to PyPI
- tox tests
- npm commands
- documentation building with Sphinx

Zuul however can support CI and CD for any language, and the library is a good
source of examples to start from when writing your own jobs. And if your jobs
are generic enough, do not hesitate to contribute upstream to enrich the library.

Provision the test1 source code
...............................

- If you went through others tutorials and **test1** already exists,
  reset the state to origin/master and remove existing files

	.. code-block:: bash

		cd test1
		git fetch --all --prune
		git reset --hard origin/master
		rm -rf .zuul.yaml *

- or clone **test1**:

	.. code-block:: bash

		git clone http://localhost:8080/test1
		cd test1
		git review -s

	You will be prompted for your username on Gerrit, use your account username.


Install this archive :download:`use-zuul-jobs.tgz <archive/use-zuul-jobs.tgz>`

This will add a ``tox.ini`` file to the repository, so unittests can be started
by running tox (obviously, make sure you have tox installed on your system first).

.. code-block:: bash

  tar -xzf /tmp/use-zuul-jobs.tgz -C .
  git add -A

Use zuul-jobs tox jobs
......................

As the **test1** source code comes with a tox file we can benefit from
the **tox-py38** and **tox-pep8** jobs defined in **zuul-jobs**.

In **test1**, create the file ``.zuul.yaml``:

.. literalinclude:: ../examples/test1-use-zuul-jobs/zuul.yaml
   :language: yaml

Then submit the change on Gerrit:

.. code-block:: bash

  git add .zuul.yaml
  git commit -m"Init test1 pipelines"
  git review

Go to Zuul `status <http://localhost:9000/t/example-tenant/status>`_ page.
2 jobs are scheduled. As nodepool has 1 node in its configuration, only
1 is running at a time and the other one is paused until the first one finishes.
You can also see that on first execution of a job, Zuul doesn't know the
aproximate job duration and progress bars are completly filled as the job
starts.

.. figure:: /images/nodepool1.gif
   :align: center

Add node in Nodepool
......................

Go to Zuul `nodes <http://localhost:9000/t/example-tenant/nodes>`_ page.
Then, open the file ``doc/sources/examples/etc_nodepool/nodepool.yaml``, and add a 2nd node,

.. literalinclude:: ../examples/etc_nodepool/nodepool-nodes.yaml
   :language: yaml

Save and wait for the node to appear in nodes page.


Go to Gerrit, Click `Reply` then type `recheck` into the text field and
click `Send`. Zuul `status <http://localhost:9000/t/example-tenant/status>`_ page
will show 2 jobs running in parallel and progress bars will fill up from
the begining.


.. figure:: /images/nodepool2.gif
   :align: center

When the jobs are completed, the produced artifacts will be stored on the log
server as usual.

This concludes this article on how to use the zuul jobs library with your projects.
