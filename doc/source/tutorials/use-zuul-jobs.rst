Zuul Hands on - Use the Zuul jobs library
-----------------------------------------

In this article, we will:

- provision a python project with a test suite based on tox
- explain how to use the `zuul-jobs library <https://opendev.org/zuul/zuul-jobs>`_ in
  order to benefit from jobs maintained by the Zuul community.

The instructions and examples below are given for a :ref:`gate_your_first_patch` setup.


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

We can now clone **test1**:

.. code-block:: bash

  git clone http://localhost:8080/test1
  cd test1
  git review -s

You will be prompted for your username on Gerrit, use your account username.

If you went through others articles of the series and **test1** already exists,
reset the state to the first initial commit in your directory and force push to
gerrit

.. code-block:: bash

  cd test1
  git reset --hard $(git log --pretty=oneline | grep "Initial commit" | awk {'print $1'} | head -1)
  git remote add gerritadmin http://admin:secret@localhost:8080/a/test1
  git push -f gerritadmin

Install this archive :download:`use-zuul-jobs.tgz <archive/use-zuul-jobs.tgz>`

This will add a **tox ini file** to the repository, so unittests can be started
by running tox (obviously, make sure you have tox installed on your system first).

.. code-block:: bash

  tar -xzf /tmp/use-zuul-jobs.tgz -C .
  git add -A

Use zuul-jobs tox jobs
......................

As the **test1** source code comes with a tox file we can benefit from
the **tox-py38** and **tox-pep8** jobs defined in **zuul-jobs**.

In **test1**, create the file **.zuul.yaml**:

.. literalinclude:: ../examples/test1-use-zuul-jobs/zuul.yaml
   :language: yaml

Then submit the change on Gerrit:

.. code-block:: bash

  git add .zuul.yaml
  git commit -m"Init test1 pipelines"
  git review

.. TODO:

   ask reader to view status, no parallel job because only 1 node
   modify nodepool and docker-compose
   restart container
   recheck
   view status, jobs in parallel

Both jobs will be started in parallel by Zuul, as can be seen in the
`status <http://localhost:9000/t/example-tenant/status>`_ page.

.. image:: /images/use-zuul-jobs-parallel-status.png
   :align: center

When the jobs are completed, the produced artifacts will be stored on the log
server as usual.

This concludes this article on how to use the zuul jobs library with your projects.
