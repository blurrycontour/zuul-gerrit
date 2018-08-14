Zuul Dashboard Javascript
=========================

zuul-web has an html, css and javascript component, `zuul-dashboard`, that
is managed using Javascript toolchains. It is intended to be served by zuul-web
directly from zuul/web/static in the simple case, or to be published to
an alternate static web location, such as an Apache server.

The web dashboard is written in `React`_ and `Patternfly`_ and is
managed by `create-react-app`_ and `yarn`_ which in turn both assume a
functioning and recent `nodejs`_ installation.

For the impatient who don't want deal with javascript toolchains
----------------------------------------------------------------

tl;dr - You have to build stuff with javascript tools.

The best thing would be to get familiar with the tools, there are a lot of
good features available. If you're going to hack on the Javascript, you should
get to know them.

If you don't want to hack on Javascript and just want to run Zuul's tests,
``tox`` has been set up to handle it for you.

If you do not have `yarn`_ installed, ``tox`` will use `nodeenv`_ to install
node into the active python virtualenv, and then will install `yarn`_ into
that virtualenv as well.

yarn dependency management
--------------------------

`yarn`_ manages the javascript dependencies. That means the first step is
getting `yarn`_ installed.

.. code-block:: console

  tools/install-js-tools.sh

The ``tools/install-js-tools.sh`` script will add apt or yum repositories and
install `nodejs`_ and `yarn`_ from them. For RPM-based distros it needs to know
which repo description file to download, so it calls out to
``tools/install-js-repos-rpm.sh``.

Once yarn is installed, getting dependencies installed is:

.. code-block:: console

  pushd web
  yarn install
  popd

The ``yarn.lock`` file contains all of the specific versions that were
installed before. Since this is an application it has been added to the repo.

To add new runtime dependencies:

.. code-block:: console

  yarn add awesome-package

To add new build-time dependencies:

.. code-block:: console

  yarn add -D awesome-package

To remove dependencies:

.. code-block:: console

  yarn remove terrible-package

Adding or removing packages will add the logical dependency to ``package.json``
and will record the version of the package and any of its dependencies that
were installed into ``yarn.lock`` so that other users can simply run
``yarn install`` and get the same environment.

To update a dependency:

.. code-block:: console

  yarn add awesome-package

Dependencies are installed into the ``node_modules`` directory. Deleting that
directory and re-running ``yarn install`` should always be safe.

Dealing with yarn.lock merge conflicts
--------------------------------------

Since ``yarn.lock`` is generated, it can create merge conflicts. Resolving
them at the ``yarn.lock`` level is too hard, but `yarn`_ itself is
deterministic. The best procedure for dealing with ``yarn.lock`` merge
conflicts is to first resolve the conflicts, if any, in ``package.json``. Then:

.. code-block:: console

  yarn install --force
  git add yarn.lock

Which causes yarn to discard the ``yarn.lock`` file, recalculate the
dependencies and write new content.

React Components
----------------

Each page is a React Component. For instance the status.html page code is
``web/src/pages/status.jsx``.

Mapping of pages/urls to components can be found in the route list in
``web/src/routes.js``.

Development
-----------

Building the code can be done with:

.. code-block:: bash

  pushd web
  yarn build
  popd

zuul-web has a ``static`` route defined which serves files from
``zuul/web/static``. ``yarn build`` doesn't put the build output files into
the ``zuul/web/static`` directory and it needs to be done manually after build.

Development server that handles things like reloading and
hot-updating of code can be started with:

.. code-block:: bash

  pushd web
  yarn start
  popd

will build the code and launch the dev server on `localhost:3000`. Fake
api response needs to be set in the ``web/public/api`` directory.

To use an existing zuul api, uses the REACT_APP_ZUUl_API_ROOT environment
variable:

.. code-block:: bash

  pushd web
  # Use openstack zuul's api:
  yarn start:openstack

  # Use software-factory multi-tenant zuul's api:
  yarn start:multi

  # Use a custom zuul:
  REACT_APP_ZUUL_API="https://zuul.example.com/api/" yarn start


Deploying
---------

The web application is a set of static files and is designed to be served
by zuul-web from its ``static`` route. In order to make sure this works
properly, the javascript build needs to be performed so that the javascript
files are in the ``zuul/web/static`` directory. Because the javascript
build outputs into the ``zuul/web/static`` directory, as long as
``npm run build`` has been done before ``pip install .`` or
``python setup.py sdist``, all the files will be where they need to be.
As long as `yarn`_ is installed, the installation of zuul will run
``npm run build`` appropriately.

Debugging minified code
-----------------------

Both the ``dev`` and ``prod`` ennvironments use the same `devtool`_
called ``source-map`` which makes debugging errors easier by including mapping
information from the minified and bundled resources to their approriate
non-minified source code locations. Javascript errors in the browser as seen
in the developer console can be clicked on and the appropriate actual source
code location will be shown.

``source-map`` is considered an appropriate `devtool`_ for production, but has
the downside that it is slower to update. However, since it includes the most
complete mapping information and doesn't impact execution performance, so in
our case we use it for both.

.. _yarn: https://yarnpkg.com/en/
.. _nodejs: https://nodejs.org/
.. _webpack: https://webpack.js.org/
.. _devtool: https://webpack.js.org/configuration/devtool/#devtool
.. _nodeenv: https://pypi.org/project/nodeenv
.. _React: https://reactjs.org/
.. _Patternfly: https://www.patternfly.org/
.. _create-react-app: https://github.com/facebook/create-react-app/blob/master/packages/react-scripts/template/README.md
