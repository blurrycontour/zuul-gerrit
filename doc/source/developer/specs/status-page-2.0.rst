Status Page 2.0
===============

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

The following specification describes the implementation of a new status page in
the Zuul UI to improve the user experience.


Motivation
----------

The current status page shows a lot of information about the different
pipelines, queues and even the individual queue items and their jobs. This
information can become quite overwhelming. Especially for larger tenants with
a lot of pipelines and longer (gate) queues the current status page becomes
more and more unusable.

For operators, this makes it hard to get a clear picture of what's going on and
for the individual developers it's hard to find their individual changes (or
queues).


Solution Approach
-----------------

The new implementation of the status page will provide both a
“operator-oriented” view and a “developer-oriented” view without mixing both
into a single view (which is kind of what the current status view tries to do).
Instead of showing all information on a single page, the new approach splits
that information into different “scopes”:

  1. Status / pipeline overview
  2. Pipeline details
  3. Individual change

Based on those scopes, the pages that handle those focus only on the relevant
information, but don't show too many details about the other scopes.


Use Cases
---------

The new status page should provide solutions for the following use cases.
Some of those are already covered by the current status page, but we list them
to ensure that we don't loose any existing functionality. The ones marked in
**bold** are not (or not fully) covered by the current status page.

As an operator, I want to:

  - see the number of queue items in each pipeline together with their current
    state (queued/waiting, running/succeeding, failing)
  - **see the most relevant/important pipelines at a glance (at the top),
    sorted by number of items [new]**
  - **be able to hide (filter out) empty pipelines and queues [new]**
  - **easily identify failing queue items**
  - be able to dequeue or promote a queue item
  - see the timestamp of the last reconfiguration
  - **see when a reconfiguration is ongoing [new]**
    This requires a backend change as the information when a reconfig is ongoing
    is not yet available.
  - see the number of events in the tenant event queues
  - **filter for specific queues and changes (maybe also projects,
    branches, ...) [new]**
  - **be able to bookmark a filtered status page [new]**

As a developer, I want to:

  - **easily identify my change in context of it's pipeline (and queue) [new]**
  - see the jobs for my change and their state (queued, running, succeeded,
    failed)
  - Find the build results for my change and also access the build logs
  - Easily identify why a job is not yet running (waiting on job dependency,
    waiting on node request, ...)
