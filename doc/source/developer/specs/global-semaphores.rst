Global Semaphores
=================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

Semaphores are useful for limiting access to resources, but their
implementation as a per-tenant configuration construct may be limiting
if they are used for real-world resources that span tenants.

This is a proposal to address that by adding global semaphores.

Background
----------

Semaphores may be used for a variety of purposes.  One of these is to
limit access to constrained resources.  Doing so allows Zuul to avoid
requesting nodes and scheduling jobs until these resources are
available.  This makes the overall system more efficient as jobs don't
need to wait for resources during their run phase (where they may be
idling test nodes which could otherwise be put to better use).

A concrete example of this is software licenses.  If a job requires
software which uses a license server to ensure that the number of
in-use seats does not exceed the available seats, a semaphore with a
max value equal to the number of available seats can be used to help
Zuul avoid starting jobs which would otherwise need to wait for a
license.

If only one Zuul tenant uses this piece of software, the existing
implementation of semaphores in Zuul is satisfactory.  But if the
software licenses are shared across Zuul tenants, then a Zuul
semaphore can't be used in this way since semaphores are per-tenant
constructs.

The general solution to sharing Zuul configuration objects across
tenants is to define them in a single git repo and include that git
repo in multiple tenants.  That works as expected for Jobs, Project
Templates, etc.  But semaphores have a definition as well as a
run-time state (whether they are aquired and by whom).  Including a
semaphore in multiple tenants essentially makes copies of that
semaphore, each with its own distinct set of holders.

Proposed Change
---------------

A new global semaphore configuration would be added to the tenant
configuration file.  Note this is the global configuration file (where
tenants are defined); not in-repo configuration where semaphores are
currently defined.

The definition would be identical to the current in-repo semaphore
configuration.  In order to grant access to only certain tenants, each
tenant will also need to specify whether that semaphore should be
available to the tenant.  This scheme is similar to the way that
authorization rules are defined in this file and then attached to
tenants.

For example:

.. code-block:: yaml

   - semaphore:
       name: licensed-software
       max: 8

   - tenant:
       name: example-tenant
       semaphores:
         - licensed-software
       source:
         gerrit:
            config-projects:
              ...

The existing in-repo semaphores will remain as they are today -- they
will not be deprecated (they are still very useful on their own for
most other use cases).

If an in-repo semaphore is defined with the same name as a global
semaphore, that will become a configuration error.  The global
semaphore will take precedence.

Implementation
--------------

The user-visible configuration is described above.

Current semaphores are stored in the ZooKeeper path
``/zuul/semaphores/<tenant>/<semaphore>``.  Global semaphores will use
a similar scheme without the tenant name:
``/zuul/global-semaphores/<semaphore>``.

Locking, releasing, and leak cleanup will all behave similarly to the
current per-tenant semaphores.  On release, a per-tenant semaphore
broadcasts a PipelineSemaphoreReleaseEvent to all pipelines in order
to trigger a pipeline run and start any jobs which may be waiting on
the semaphore.  A global semaphore will do the same, but for every
pipeline of every tenant which includes the semaphore.

Alternatives
------------

We could add a field to the in-repo definitions of semaphores which
indicates that the semaphore should be global.  As this has the
ability to affect other tenants, we would need to restrict this to
config-projects only.  However, that still opens the possibility of
one tenant affecting another via the contents of a config-project.
Some method of allowing the administrator to control this via the
tenant config file would still likely be necessary.  As long as that's
the case, it seems simpler to just define the semaphores there too.

We could outsource this to Nodepool.  In fact, having nodepool manage
resources like this seems like a natural fit.  However, the current
Nodepool implementation doesn't permit more than one provider to
satisfy a node request, so a hypothetical semaphore provider wouldn't
be able to be combined with a provider of actual test nodes.
Addressing this is in-scope and a worthwhile change for Nodepool, but
it is potentially a large and complex change.  Additionally, the idea
of waiting for a semaphore before submitting requests for real
resources adds a new dimension to even that idea -- Nodepool would
need to know whether to run the semaphore provider first or last
depending on the desired resource aquisition order.  Meanwhile, since
Zuul does have the concept of semaphores already and they almost fit
this use case, this seems like a reasonable change to make in Zuul
regardless of any potential Nodepool changes.
