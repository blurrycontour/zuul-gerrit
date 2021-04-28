=========================
Resource Quota per Tenant
=========================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.


Problem Description
===================

Zuul is inherently built to be tenant scoped and can be operated as a shared CI
system for a large number of more or less independent projects. As such, one of
its goals is to provide each tenant a fair amount of resources.

If Zuul, and more specifically Nodepool, are pooling build nodes from shared
providers (e.g. a limited number of OpenStack clouds) the principle of a fair
resource share across tenants can hardly be met by the Nodepool side. In large
Zuul installations, it is not uncommon that some tenants request far more
resources and at a higher rate from the Nodepool providers than other tenants.
While Zuuls "fair scheduling" mechanism makes sure each queue item gets treated
justly, there is no mechanism to limit allocated resources on a per-tenant
level. This, however, would be useful in different ways.

For one, in a shared pool of computing resources, it can be necessary to
enforce resource budgets allocated to tenants. That is, a tenant shall only be
able to allocate resources within a defined and payed limit. This is not easily
possible at the moment as Nodepool is not inherently tenant-aware. While it can
limit the number of servers, CPU cores, and RAM allocated on a per-pool level,
this does not directly translate to Zuul tenants. Configuring a separate pool
per tenant would not only lead to much more complex Nodepool configurations,
but also induce performance penalties as each pool runs in its own Python
thread.

Also, in scenarios where Zuul and auxiliary services (e.g. GitHub or
Aritfactory) are operated near or at their limits, the system can become
unstable. In such a situation, a common measure is to lower Nodepools resource
quota to limit the number of concurrent builds and thereby reduce the load on
Zuul and other involved services. However, this can currently be done only on
a per-provider or per-pool level, most probably affecting all tenants. This
would contradict the principle of fair resource pooling as there might be less
eager tenants that do not, or rather insignificantly, contribute to the overall
high load. It would therefore be more advisable to limit only those tenants'
resources that induce the most load.

Therefore, it is suggested to implement a mechanism in Nodepool that allows to
define and enforce limits of currently allocated resources on a per-tenant
level. This specification describes how resource quota can be enforced in
Nodepool with minimal additional configuration and execution overhead and with
little to no impact on existing Zuul installations.


Proposed Change
===============

Make Nodepool Tenant Aware
--------------------------

1. Add "tenant" attribute to zk.NodeRequest (applies to Zuul and
   Nodepool)
2. Add "tenant" attribute to zk.Node (applies to Nodepool)

Introduce Tenant Quotas in Nodepool
-----------------------------------

1. introduce new top-level config item ``tenant-resources`` for Nodepool config

   .. code-block:: yaml

      tenant-resources:
        tenant1:
          max-servers: 10
          max-cores: 200
          max-ram: 800
        tenant2:
          max-servers: 100
          max-cores: 1500
          max-ram: 6000

2. for each node request that has the tenant attribute set and a corresponding
   ``tenant-resources`` config exists

   - get quota information from current active and planned nodes of same tenant
   - if quota for current tenant would be exceeded

     - defer node request
     - do not pause the pool (as opposed to exceeded pool quota)
     - leave the node request unfulfilled (REQUESTED state)
     - return from handler for another iteration to fulfill request when tenant
       quota allows eventually

   - if quota for current tenant would not be exceeded
   
     - proceed with normal process if tenant quota is not exceeded

3. for each node request that does not have the tenant attribute or a tenant
   for which no ``tenant-resources`` config exists

   - do not calculate the per-tenant quota and proceed with normal process

Implementation Caveats
----------------------

This implementation is ought to be driver agnostic and therefore not to be
implemented separately for each Nodepool driver. For the Kubernetes, OpenShift,
and Static drivers, however, it is not easily possible to find the current
allocated resources. This change therefore does not apply to these. The
Kubernetes and OpenShift(Pods) drivers would need to enforce resource request
attributes which are optional at the moment (cf. `Kubernetes Driver Doc`_). How
these ``tenant-resources`` can be implemented in this case needs to be
addressed separately.

In the `QuotaSupport`_ mixin class, we already query ZooKeeper for the used and
planned resources. Ideally, we can extend this method to also return the
resources currently allocated by each tenant without additional costs and
account for this additional quota information as we already do for provider and
pool quotas (cf. `SimpleTaskManagerHandler`_)


.. _`Kubernetes Driver Doc`: https://zuul-ci.org/docs/nodepool/kubernetes.html#attr-providers.[kubernetes].pools.labels.cpu
.. _`QuotaSupport`: https://opendev.org/zuul/nodepool/src/branch/master/nodepool/driver/utils.py#L180
.. _`SimpleTaskManagerHandler`: https://opendev.org/zuul/nodepool/src/branch/master/nodepool/driver/simple.py#L218
