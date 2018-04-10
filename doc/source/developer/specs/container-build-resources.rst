Use Kubernetes for Build Resources
==================================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

There has been a lot of interest in using containers for build
resources in Zuul.  The use cases are varied, so we need to describe
in concrete terms what we aim to support.  Zuul provides a number of
unique facilities to a CI/CD system which are well-explored in the
full-system context (i.e., VMs or bare metal) but it's less obvious
how to take advantage of these features in a container environment.
As we design support for containers it's also important that we
understand how things like speculative git repo states and job content
will work with containers.

In this document, we will consider two general approaches to using
containers as build resources:

* Containers that behave like a machine
* Native container workflow

Finally, there are a multiple container environments.  Kubernetes and
OpenShift (an open source distribution of Kubernetes) are popular
environments which provide significant infrastructure to help us more
easily integrate them with Zuul, so this document will focus on these.
We may be able to extend this to other environments in the future.

.. _container-machine:

Containers That Behave Like a Machine
-------------------------------------

In some cases users may want to run scripted job content in an
environment that is more lightweight than a VM.  In this case, we're
expecting to get a container which behaves like a VM.  The important
characteristic of this scenario are that the job is not designed
specifically as a container-specific workload (e.g., it might simply
be a code style check).  It could just as easily run on a VM as a
container.

To achieve this, we should expect that a job defined in terms of
simple commands should work.  For example, a job which runs a playbook
with::

  hosts: all
  tasks:
    - command: tox -e pep8

Should work given an appropriate base job which prepares a container.

A user might expect to request a container in the same way they
request any other node::

  nodeset:
    nodes:
      - name: controller
        label: python-container

To provide this support, nodepool would need to create the requested
container.  Containers in Kubernetes always run a single command, and
when that command is finished, the container terminates.  Nodepool
doesn't have the context to run a command at this point, so instead,
it can create a container running a command that can simply run
forever, for example, ``/bin/sh``.

Zuul can then add the container to the inventory using the `kubectl
connection plugin`_.  It will then be able to run additional commands in
the container -- the commands which comprise the actual job.

Strictly speaking, this is all that is required for basic support in
Zuul, but as discussed in the introduction, we need to understand how
to build a complete solution including dealing with the speculative
git repo state.

A base job can be constructed to update the git repos inside the
container, and retrieve any artifacts produced.  We should be able to
have the same base job detect whether there are containers in the
inventory and alter behavior as needed to accomodate them.  For a
discussion of how the git repo state can be synchronised, see
:ref:`git-repo-sync`.

.. _kubectl connection plugin: https://docs.ansible.com/ansible/2.5/plugins/connection/kubectl.html

.. _container-native:

Native Container Workflow
-------------------------

A workflow that is designed from the start for containers may behave
very differently.  In particular, it's likely to be heavily image
based, and may have any number of containers which may be created and
destroyed in the process of executing the job.

It may use the `k8s_raw Ansible module`_ to interact directly with
Kubernetes, creating and destroying pods for the job in much the same
way that an existing job may use Ansible to orchestrate actions on a
worker node.

All of this means that we should not expect Nodepool to provide a
running container -- the job itself will create containers as needed.
It also means that we need to think about how a job will use the
speculative git repos.  It's very likely to need to build custom
images using those repos which are then used to launch containers.

Let's consider a job which begins by building container images from
the speculative git source, then launches containers from those images
and exercises them.

.. note:: It's also worth considering a complete job graph where a
   dedicated job builds images and subsequent jobs use them.  We'll
   deal with that situation in :ref:`buildset`.

Within a single job, we could build images by requesting either a full
machine or a :ref:`container-machine` from Nodepool and running the
image build on that machine.  Or we could use the `k8s_raw Ansible
module`_ to create that container from within the job.  We would use the
:ref:`git-repo-sync` process to get the appropriate source code onto
the builder.  Regardless, once the image builds are complete, we can
then use the result in the remainder of the job.

In order to use an image (regardless of how it's created) Kubernetes
is going to expect to be able to find the image in a repository it
knows about.  Putting images created based on speculative future git
repo stats into a public image repository may be confusing, and
require extra work to clean those up.  Therefore, the best approach
may be to work with private, per-build image repositories.

OpenShift provides some features that make this easier, so we'll start
there.

We can ask Nodepool to create an `OpenShift project`_ for the use of
the job.  That will create a private image repository for the project.
Service accounts in the project are automatically created with
``imagePullSecrets`` configured to use the private image repository [#f1]_.
We can have Zuul use one of the default service accouns, or have
Nodepool create a new one specifically for Zuul, and then when using
the `k8s_raw Ansible module`_, the image registry will automatically be
used.

With some work, we may be able to emulate the same for plain
Kubernetes, but we may want to focus on OpenShift first and see if
Kubernetes intends to add similar features.

.. _OpenShift Project: https://docs.openshift.org/latest/dev_guide/projects.html
.. [#f1] https://docs.openshift.org/latest/dev_guide/managing_images.html#using-image-pull-secrets
.. _k8s_raw Ansible module: http://docs.ansible.com/ansible/2.5/modules/k8s_raw_module.html

.. _git-repo-sync:

Synchronizing Git Repos
-----------------------

Our existing method of synchronizing git repositories onto a worker
node relies on SSH.  It's possible to run an SSH daemon in a container
(or pod), but if it's otherwise not needed, it may be considered too
cumbersome.  In particular, it may mean establishing a service entry
in kubernetes and an ingress route so that the executor can reach the
SSH server.  However, it's always possible to run commands in a
container using kubectl with direct stdin/stdout connections without
any of the service/ingress complications.  It should be possible to
adapt our process to use this.

Our current process will use a git cache if present on the worker
image.  This is optional -- a Zuul user does not need a specially
prepared image, but if one is present, it can speed up operation.  In
a container environment, we can similarly have Nodepool build
container images with a git repo cache.  The next step in the process
can either start with one of those, or any other base image.

Create a new pod based on either the git repo cache image, or a base
image.  Ensure it has ``git`` installed.  If the pod is going to be
used to run a single command (i.e., :ref:`container-machine`, or will
only be used to build images), then a single container is sufficient.
However, if the pod will support multiple containers, each needing
access to the git cache, then we can use the `sidecar pattern`_ to
update the git repo once.  In that case, in the pod definition, we
should specify an `emptyDir volume`_ where the final git repos will be
placed, and other containers in the pod can mount the same volume.

Run commands in the container to copy the cached git repos (if any) to
the destination path.

Run commands in the container to push the updated git commits.  In
place of the normal ``git push`` command which relies on SSH, use a
custom SSH command which uses kubectl to set up the remote end of the
connection.

Here is an example custom ssh script:

.. code-block:: bash

   #!/bin/bash

   /usr/bin/kubectl exec zuultest -c sidecar -i /usr/bin/git-receive-pack /zuul/glance

Here is an example use of that script to push to a remote branch:

.. code-block:: console

   [root@kube-1 glance]# GIT_SSH="/root/gitssh.sh" git push kube HEAD:testbranch
   Counting objects: 3, done.
   Delta compression using up to 4 threads.
   Compressing objects: 100% (3/3), done.
   Writing objects: 100% (3/3), 281 bytes | 281.00 KiB/s, done.
   Total 3 (delta 2), reused 0 (delta 0)
   To git+ssh://kube/
    * [new branch]        HEAD -> testbranch

.. _sidecar pattern: https://docs.microsoft.com/en-us/azure/architecture/patterns/sidecar
.. _emptyDir volume: https://kubernetes.io/docs/concepts/storage/volumes/#emptydir

.. _buildset:

BuildSet Resources
------------------

It may be very desirable to construct a job graph which builds
container images once at the top, and then supports multiple jobs
which deploy and exercise those images.  The use of a private image
registry is particularly suited to this.  We should explore ways of
supporting this use case.

On the other hand, folks may want jobs in a buildset to be completely
isolated from each other, so we may not want to simply assume that all
jobs in a buildset are related and use the same image registry.

Some ideas we could explore:

* When a job graph with dependencies are created, assume all jobs with
  dependencies use the same OpenShift project/registry.

* Allow a user to specify whether a project's scope is the job, or the
  buildset.

* Don't rely on the OpenShift per-project image registry at all, and
  instead implement it using Kubernetes primitives in a job at the top
  of the buildset.  Add a facility that would allow the user to tell
  Zuul to keep the resources used by that job (i.e., the registry
  service) continually running until the end of the buildset.

In order to support this, we may need to implement provider affinity
for builds in a buildset in Nodepool so that we don't have to deal
with ingress access to the registry (which may not be possible).
