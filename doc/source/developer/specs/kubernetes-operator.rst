Kubernetes Operator
===================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

While Zuul can be happily deployed in a Kubernetes environment, it is
a complex enough system that a Kubernetes Operator could provide value
to deployers. A Zuul Operator would allow a deployer to create "A Zuul"
in their Kubernetes and leave the details of how that works to the
Operator.

To that end, the Zuul Project should create and maintain a Kubernetes
Operator for running Zuul. Given the close ties between Zuul and Ansible,
we should use `Ansible Operator`_ to implement the Operator. Our existing
community is already running Zuul in both Kubernetes and OpenShift, so
we should ensure our Operator works in both. When we're happy with it,
we should publish it to `OperatorHub`_.

That's the easy part. The remainder of the document is for hammering out
some of the finer details.

.. _Ansible Operator: https://github.com/operator-framework/operator-sdk/blob/master/doc/ansible/user-guide.md
.. _OperatorHub: https://www.operatorhub.io/

Custom Resource Definitions
---------------------------

One of the key parts of making an Operator is to define one or more
Custom Resource Definition (CRD). These allow a user to say "hey k8s,
please give me a Thing". It is then the Operator's job to take the
appropriate actions to make sure the Thing exists.

For Zuul, there should definitely be a Zuul CRD. It should be namespaced
with ``zuul-ci.org``, so for sake of argument, using it should start
off looking like:

::

  apiVersion: zuul-ci.org/v1alpha1
  kind: Zuul

While Zuul requires Nodepool to operator, there are friendly people
using Nodepool without Zuul. There should then also be a Nodepool CRD,
something like:

::

  apiVersion: zuul-ci.org/v1alpha1
  kind: Nodepool


Images
------

The Operator should, by default, use the ``docker.io/zuul`` images that
are published. To support locally built or overridden images, the Operator
should have optional config settings for each image.

External Dependencies
---------------------

Zuul needs some services, such as a RDBMS and a Zookeeper, that themselves
are resources that should be managed by an Operator. It is out of scope
(and inappropriate) for Zuul to provide these itself. Instead, the Zuul
Operator should use CRDs provided by other Operators.

On Kubernetes installs that support the Operator Lifecycle Manager, external
dependencies can be declared in the Zuul Operator's OLM metadata. However,
not all Kubernetes installs can handle this, so it should also be possible
for a deployer to manually install a list of documented operators and CRD
definitions before installing the Zuul Operator.

The Operator should provide config override settings to allow a deployer to say "I already have one of these that's located at Location, please don't create
one."

Zuul supports multiple backends for some things, such as supporting both
MySQL and PostGres. The Zuul Operator should not attempt to support managing
both, but instead should pick one and allow deployers who wish to use a
different one to use the config override setting pointing to the DB location.

Zuul Config
-----------

Zuul config files that do not contain information that the Operator needs to
do its job, or that do not contain information into which the Operator might
need to add data, should be handled by ConfigMap or Secret objects and not as
parts of the CRD. The CRD should take references to the ConfigMap/Secret
objects.

On the other hand, in cases like the ``zuul.conf`` config controlling the
connections, the Operator needs to make decisions based on what's going to
go there, or needs to add information about services it is also controlling
on behalf of the deployer, like RDBMS and Zookeeper connection info, the
information should exist in the CRD as parameters.

Concretely, completely external files like ``clouds.yaml`` and ``kube/config``
should be in Secrets referenced in the config. Zuul files like 
``nodepool.yaml`` and ``main.yaml`` that contain no information the Operator
needs should be in ConfigMaps and referenced. Zuul files like 
 ``/etc/nodepool/secure.conf`` and ``/etc/zuul/zuul.conf`` should be managed
by the Operator and be represented in the CRD.

The Zuul Operator should manage logging config.
