Zuul Hands on - Use the Zuul jobs library
-----------------------------------------

In this article, we will:

- provision a python project with a test suite based on tox
- explain how to use the `zuul-jobs library <https://opendev.org/zuul/zuul-jobs>`_ in
  order to benefit from jobs maintained by the Zuul community.

The instructions and examples below are given for a :ref:`quick_start` setup.


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

.. code-block:: bash

  git clone http://localhost:8080/test1
  cd test1
  git review -s


.. TODO: figure out project template setup instruction

This will add a **tox ini file** to the repository, so unittests can be started
by running tox (obviously, make sure you have tox installed on your system first).

.. code-block:: bash

  tox

If you went through the previous article of the series to the end, remove also
the previous jobs and pipelines definitions, and the now useless hello.py file:

.. code-block:: bash

  git rm -r playbooks .zuul.yaml hello.py

Push the code to the **test1** repository. Note that we don't use **git review**
here to bypass the review process of Gerrit. We will reconfigure the CI later.

.. code-block:: bash

  git add -A
  git commit -m"Initialize test1 project"
  git push gerrit


Use zuul-jobs tox jobs
......................

As the **test1** source code comes with a tox file we can benefit from
the **tox-py36** and **tox-pep8** jobs defined in **zuul-jobs**.

In **test1**, create the file **.zuul.yaml**:

.. code-block:: yaml

  - project:
      check:
        jobs:
          - tox-py27
          - tox-pep8
      gate:
        jobs:
          - tox-py27
          - tox-pep8

Then submit the change on Gerrit:

.. code-block:: bash

  git add .zuul.yaml
  git commit -m"Init test1 pipelines"
  git review

Both jobs will be started in parallel by Zuul, as can be seen in the
`status <http://localhost:9000/t/example-tenant/status>`_ page.

.. TODO: add screenshot

When the jobs are completed, the produced artifacts will be stored on the log
server as usual.

This concludes this article on how to use the zuul jobs library with your projects.
