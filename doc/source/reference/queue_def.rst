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
