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
  spec:
    merger:
      count: 5
    executor:
      count: 5
    web:
      count: 1

    
While Zuul requires Nodepool to operate, there are friendly people
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

::

  apiVersion: zuul-ci.org/v1alpha1
  kind: Zuul
  spec:
    merger:
      count: 5
      image: docker.io/example/zuul-merger
    executor:
      count: 5
    web:
      count: 1

External Dependencies
---------------------

Zuul needs some services, such as a RDBMS and a Zookeeper, that themselves
are resources that should or could be managed by an Operator. It is out of
scope (and inappropriate) for Zuul to provide these itself. Instead, the Zuul
Operator should use CRDs provided by other Operators.

On Kubernetes installs that support the Operator Lifecycle Manager, external
dependencies can be declared in the Zuul Operator's OLM metadata. However,
not all Kubernetes installs can handle this, so it should also be possible
for a deployer to manually install a list of documented operators and CRD
definitions before installing the Zuul Operator.

For each external service dependency where the Zuul Operator would be relying
on another Operator to create and manage the given service, there should be
a config override setting to allow a deployer to say "I already have one of
these that's located at Location, please don't create one." The config setting
should be the location and connection information for the externally managed
version of the service, and not providing that information should be taken
to mean the Zuul Operator should create and manage the resource.

While Zuul supports multiple backends for RDBMS, the Zuul Operator should not
attempt to support managing both. If the user chooses to let the Zuul Operator
create and manage RDBMS, the `Percona XtraDB Cluster Operator`_ should be
used. Deployers who wish to use a different one should use the config override
setting pointing to the DB location.

.. _Percona XtraDB Cluster Operator: https://operatorhub.io/operator/percona-xtradb-cluster-operator

Zuul Config
-----------

Zuul config files that do not contain information that the Operator needs to
do its job, or that do not contain information into which the Operator might
need to add data, should be handled by ConfigMap resources and not as
parts of the CRD. The CRD should take references to the ConfigMap objects.

On the other hand, in cases like the ``zuul.conf`` config controlling the
connections, the Operator needs to make decisions based on what's going to
go there, or needs to add information about services it is also controlling
on behalf of the deployer, like RDBMS and Zookeeper connection info. For these,
one or more ``ZuulConnection`` CRDs should be used:

::

  apiVersion: zuul-ci.org/v1alpha1
  kind: ZuulConnection
  spec:
    name: gerrit
    settings:
      name: gerrit
      driver: gerrit
      server: gerrit
      sshkey: /var/ssh/zuul
      user: zuul
      baseurl: http://gerrit:8080
      auth_type: basic

In addition to ``zuul.conf`` settings the Operator needs to create and manage,
there may also be additional user-provided ``zuul.conf`` settings, such as
github app certificates or gerrit ssh key. It should be possible for the
deployer to provide references to one or more ``Secret`` resources that can
be bind-mounted in to ``/etc/zuul/conf.d``:

::

  apiVersion: zuul-ci.org/v1alpha1
  kind: ZuulConnection
  spec:
    name: gerrit
    secretname: GerritPassword

A ``ZuulConnection`` cannot specify both a secret reference and a set of
settings.

Concretely, completely external files like ``clouds.yaml`` and ``kube/config``
should be in Secrets referenced in the config. Zuul files like
``nodepool.yaml`` and ``main.yaml`` that contain no information the Operator
needs should be in ConfigMaps and referenced. Zuul files like
 ``/etc/nodepool/secure.conf`` and ``/etc/zuul/zuul.conf`` should be managed
by the Operator and be represented in the CRD.

.. warning:: Should we have a list of ZuulConnection resources in the Zuul
   CRD? Or should we have each ZuulConnection specify the Zuul they are for?

Logging
-------

By default, the Zuul Operator should perform no logging config which should
result in Zuul using its default of logging to ``INFO``. There should be a
simple config option to switch that to enable ``DEBUG`` logging. There should
also be an option to allow specifying a named ``ConfigMap`` with a logging
config. If a logging config ``ConfigMap`` is given, it should override the
``DEBUG`` flag.
