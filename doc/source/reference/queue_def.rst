.. _queue:

Queue
=====

Projects that interact with each other should share a ``queue``.
This is especially used in a :value:`dependent <pipeline.manager.dependent>`
pipeline. The :attr:`project.queue` can optionally refer
to a specific :attr:`queue` object that can further configure the
behavior of the queue.

Here is an example ``queue`` configuration.

.. code-block:: yaml

   - queue:
       name: integrated
       per-branch: false


.. attr:: queue

   The attributes available on a queue are as follows (all are
   optional unless otherwise specified):

   .. attr:: name
      :required:

      This is used later in the project definition to refer to this queue.

   .. attr:: per-branch
      :default: false

      Queues by default define a single queue for all projects and
      branches that use it. This is especially important if projects
      want to do upgrade tests between different branches in
      the :term:`gate`. If a set of projects doesn't have this use case
      it can configure the queue to create a shared queue per branch for
      all projects. This can be useful for large projects to improve the
      throughput of a gate pipeline as this results in shorter queues
      and thus less impact when a job fails in the gate. Note that this
      means that all projects that should be gated must have aligned branch
      names when using per branch queues. Otherwise changes that belong
      together end up in different queues.

   .. attr:: allow-circular-dependencies
      :default: false

      Define if Zuul is allowed to process circular dependencies between
      changes for this queue. All projects that are part of a dependency cycle
      must share the same change queue.

      In case Zuul detects a dependency cycle it will make sure that every
      change also includes all other changes that are part of the cycle.
      However each change will still be a normal item in the queue with its own
      jobs.

      Reporting of success will be postponed until all items in the cycle
      succeeded. In case of a failure in any of those items the whole cycle
      will be dequeued.

      An error message will be posted to all items of the cycle in case some
      items fail to report (e.g. merge failure when some items were already
      merged). In this case the target branch(es) might be in a broken state.

      In general, circular dependencies are considered to be an
      antipattern since they add extra constraints to continuous
      deployment systems.  Additionally, due to the lack of atomicity
      in merge operations in code review systems, it may be possible
      for only part of a cycle to be merged.  In that case, manual
      interventions (such as reverting a commit, or bypassing gating to
      force-merge the remaining commits) may be required.

      .. warning:: If the remote system is able to merge the first but
                   unable to merge the second or later change in a
                   dependency cycle, then the gating system for a
                   project may be broken and may require an
                   intervention to correct.
