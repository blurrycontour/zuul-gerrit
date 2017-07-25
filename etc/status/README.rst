Zuul Status
===========

Zuul Status is a web portal for a Zuul server.

Install Depends
---------------

The web application is managed by `yarn`_ and `webpack`_ which in turn both
assume a functioning and recent ``npm`` installation.

The ``boostrap.sh`` script will add apt or yum repositories and install
npm and yarn from them. Once yarn is installed, getting dependencies installed
is:

.. code-block:: bash

  yarn install

The ``yarn.lock`` file contains all of the specific versions that were
installed before. Since this is an application it has been added to the repo.

To add new dependencies:

.. code-block:: bash

  yarn add awesome-package

and to remove dependencies:

.. code-block:: bash

  yarn remove terrible-package

Development
-----------

`webpack`_ takes care of bundling web assets for deployment, including tasks
such as minifying and transpiling for older browsers. It takes a
javascript-first approach, and generates an index.html that includes the
appropriate javascript and CSS to get going. It includes a development server
that handles things like reloading and hot-updating of code, so in general
it is recommended to run the following in a terminal somewhere:

.. code-block:: bash

 npm run start

Which will build the code, launch the dev server and open the URL in a browser.
It will additionally watch for changes to the files and re-compile/refresh as
needed. By default it will use the 'basic' demo data that's built-in. If you
want to see more advanced data:

.. code-block:: bash

  # Run against openstack built-in demo data
  npm run start:openstack

  # Run against tree built-in demo data
  npm run start:tree

  # Run against live data from OpenStack's Zuul
  npm run start:live

  # Run against live data from OpenStack's Zuulv3
  npm run start:livev3

Deploying
---------

The web application is intended to be served as static files. There is a
command to prepare the ``dist`` directory with production files:

.. code-block:: bash

  npm run build:dist

The contents of ``dist`` are then suitable for serving via any static web
server.

.. _yarn: https://yarnpkg.com/en/
.. _webpack: https://webpack.js.org/
