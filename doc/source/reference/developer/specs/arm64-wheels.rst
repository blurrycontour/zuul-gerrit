============
ARM64 Wheels
============

https://storyboard.openstack.org/

Problem Description
===================

We wish to produce nodepool containers for the ARM64 platform.  Mostly
this is because `diskimage-builder` does not have any ability to
cross-build, so building images for ARM64 clouds requires an
ARM64-based nodepool-builder instance.  However, it is generically
helpful to have multi-arch containers for what is becoming an
increasingly popular server platform.

We use the cross-build features of `docker buildx` to produce both
x86-64 and ARM64 containers for nodepool.  This uses binary emulation
(via `qemu`) to produce ARM64-based containers on an x86-64 host in
the gate.

The `nodepool` containers are built on top of the `python-builder`
images provided by OpenDev (in `system-config`).  These images are
based ontop of the offical `python` container images.  These upstream
images are further based on the Debian platform (images are available
based on `stable` and `oldstable`).  These images include a
custom-built Python version of your choosing in `/usr/local/` along
with standard Debian libraries in the base system (it is important to
note that these images do *not* use the packaged Python of the
underlying Debian image).

Several `nodepool` Python requirements have binary dependencies and
require a compilation stage when building the containers.
Cross-compiling to make binary ARM64 Python wheels under `buildx` can
be very slow, to the point it becomes impractical to run in the gate.

Constraints of OpenDev wheels
-----------------------------

Currently we use a small hack to `pip.conf
<https://opendev.org/zuul/nodepool/src/branch/master/tools/pip.conf.arm64>`__
to use wheels built by OpenDev in the nodepool container build.

The problem with this approach is that OpenDev wheels are built for a
specific platform, *not* a specific Python version.

So, for example, OpenDev builds ARM64 wheels for Debian `bullseye`
using the packaged Python intpreter (currently 3.9).  Although
`nodepool` uses `bullseye` as the base platform, it may choose any
Python supported by the upstream container images.

For example, if `nodepool` wanted to use a `python-3.11-bullseye`
container the OpenDev wheels will be built against the correct
libraries, but for Python 3.9 instead of 3.11.

The practical result is that `nodepool` containers are constrained to
only using the Python version "native" to the underlying distribution.

Possible solutions
==================

* Maintain the status quo.  Practically that means

  * continuing to choose a container with an underlying platform
    supported by OpenDev wheels
  * continuing to use the same Python version on that container as the
    base-system uses as its "native" container

* Expand OpenDev wheel generation to produce wheels for alternative
  Python versions.  OpenDev has generally had a "platform" focus since
  most of the testing is designed to work on specific generic
  platforms environments (`ubuntu-bionic`, `ubuntu-focal`, `centos-8`,
  etc.)

  * Add volumes to `<http://mirror.iad.rax.opendev.org/wheel/>`__
  * Update wheel build infrastructure to be able to use Python from
    upstream containers to build/publish
  * Make sure extant mirror setup isn't affected
  * Update jobs to build range of new wheels like
    `debian-11-py310-aarch64`, etc.
  * Update nodepool to use these mirrors

* Create a custom cache.  Nodepool could somehow run a periodic job or
  similar to produce the wheels it requires and source this during
  build.

* Avoid this problem by building "manylinux" universal ARM64 wheels
  for any binary components.  We have some experience helping build
  generic wheels with the `pyca/cryptography` project.  There is no
  generic solution to this, however.  It involves building specific
  static libraries against specific environments using the "manylinux"
  tooling.  The wheels actually referenced:

  * `/wheel/debian-11-aarch64/prettytable/prettytable-0.7.2-py3-none-any.whl`
  * `/wheel/debian-11-aarch64/voluptuous/voluptuous-0.12.2-py3-none-any.whl`
  * `/wheel/debian-11-aarch64/pynacl/PyNaCl-1.4.0-cp39-cp39-linux_aarch64.whl`
    (see `<https://github.com/pyca/pynacl/issues/601>`__)
  * `/wheel/debian-11-aarch64/netifaces/netifaces-0.11.0-cp39-cp39-linux_aarch64.whl`
  * `/wheel/debian-11-aarch64/cffi/cffi-1.15.0-cp39-cp39-manylinux_2_17_aarch64.manylinux2014_aarch64.whl`
  * `/wheel/debian-11-aarch64/ruamel-yaml-clib/ruamel.yaml.clib-0.2.6-cp39-cp39-linux_aarch64.whl`
  * `/wheel/debian-11-aarch64/pycparser/pycparser-2.20-py2.py3-none-any.whl`
  * `/wheel/debian-11-aarch64/yappi/yappi-1.3.3-cp39-cp39-linux_aarch64.whl`

Proposed Change
===============

A combination of expanding the OpenDev wheel generation for more
arbitrary Python versions and working with as many upstream projects
to produce generic wheels seems the most useful way forward.

Implementation
==============

Assignee(s)
-----------

Primary assignee:
  tbd

.. feel free to add yourself as an assignee, the more eyes/help the better

Gerrit Topic
------------

Use Gerrit topic "zuul_arm64_wheels" for all patches related to this spec.

.. code-block:: bash

    git-review -t zuul_arm64_wheels

Work Items
----------

TBD

Documentation
-------------

TBD

Security
--------

TBD

Testing
-------

TBD

Follow-up work
--------------

TBD

Dependencies
============

TBD
