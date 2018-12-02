Scale out scheduler
===================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

Zuul has a microservices architecture with the goal of no single point of
failure in mind. This has not yet been achieved for the zuul-scheduler
component.

Especially within large Zuul deployments with many also long running jobs the
cost of a scheduler crash can be quite high. In this case currently all
in-flight jobs are lost and need to be restarted. A scale out scheduler approach
can avoid this.

The same problem holds true when updating the scheduler. Currently there is no
possibility to upgrade the scheduler without downtime. While the pipeline state
can be saved and re-enqueued this still looses all in-flight jobs. Further on a
larger deployment the startup of the scheduler easily can be in the multi minute
range. Having the ability to do zero downtime upgrades can make updates much
more easier.

Further having multiple schedulers can facilitate parallel processing of several
tenants and help reducing global locks within installations with many tenants.

In this document we will outline an approach towards a completely single point
of failure free zuul system. This will be a transition with multiple phases.


Status quo
----------

Zuul is an event driven system with several event loops that interact with each
other:

* Driver event loop: Drivers like Github or Gerrit have its own event loops.
  They perform preprocessing of the received events and add events into the
  scheduler event loop.

* Scheduler event loop: This event loop processes the pipelines and
  reconfigurations.

All of these event loops currently run within the scheduler process without
persisting their state. So the path to a scale out scheduler involves mainly
making all event loops scale out capable.



Target architecture
-------------------

In addition to the event loops mentioned above we need an additional event queue
per tenant. This will make it easy to process several tenants in parallel. A new
driver event would first be processed in the driver event queue. This will add a
new event into the scheduler event queue. The scheduler event queue then checks
which tenants may be interested in this event according to the tenant
configuration. Base on this the event dispatched to all matching tenant queues.

As it is today different event types will have different priorities. This will
be expressed like in node-requests with a prefix.

The event queues will be stored in Zookeeper in the following paths:

* ``/zuul/events/connection/<connection name>/<sequence>``: Event queue of a
  connection

* ``/zuul/events/scheduler-global/<prio>-<sequence>``: Global event queue of
  scheduler

* ``/zuul/events/tenant/<tenant name>/<prio>-<sequence>``: Tenant event queue

In order to make reconfigurations efficient we also need to store the parsed
branch config in Zookeeper. This makes it possible to create the current layout
without the need to ask the mergers multiple times for the configuration. This
also can be used by zuul-web to keep an up-to-date layout that can be used for
api requests.

We also need to store the pipeline state in Zookeeper. This will be similar to
the status.json but also needs to contain the frozen jobs and their current
state.

Further we need to replace gearman by Zookeeper as rpc mechanism to the
executors. This will make it possible that different schedulers can continue
smoothly with pipeline execution. The jobs will be stored in
``/zuul/jobs/<tenant>/<sequence>``.


Driver event ingestion
----------------------

Currently the drivers immediately get events from Gerrit or Github, process them
and forward the events to the scheduler event loop. Thus currently all events
are lost during a downtime of the zuul-scheduler. In order to decouple this we
can push the raw events into Zookeeper and pop them in the driver event loop.

We will split the drivers into an event receiving and an event processing
component. The event receiving component will store the events in a squenced
znode in the path ``/events/connection/<connection name>/<sequence>``.
The event receiving part may or may not run within the scheduler context.
The event processing part will be part of the scheduler context.

There are three types of event receive mechanisms in Zuul:

* Active event gathering: The connection actively subscribes for events (Gerrit)
  or generates them itself (git, timer, zuul)

* Passive event gathering: The events are sent to zuul from outside (Github
  webhooks)

* Internal event generation: The events are generated within zuul itself and
  typically get injected directly into the scheduler event loop and thus don't
  need to be changed in this phase.

The active and passive event gathering need to be handled slightly different.

Active event gathering
~~~~~~~~~~~~~~~~~~~~~~

This is mainly done by the Gerrit driver. We actively maintain a connection to
the target and receive events. This means that if we have more than one instance
we need to find a way to handle duplicated events. This type of event gathering
can run within the scheduler process. However while we don't have multiple
scheduler support yet at this stage we may want to be able to start this as a
separate process or include it in zuul-web.

**Variant A**

We can utilize leader election to make sure there is exactly one instance
receiving the events. This makes sure that we don't need to handle duplicated
events at all. A drawback is that there is a short time when the current leader
stops until the next leader has started event gathering. This could lead to a
few missed events.

**Variant B**

All instances receive events and store them in Zookeeper. The event processing
part now need to take care of deduplicating the events. This could be done by
storing the hashes of the event payload of the last x minutes and ignoring any
event that is duplicated.

Although slightly more complicated we probably should go with variant B.

Passive event gathering
~~~~~~~~~~~~~~~~~~~~~~~

In case of passive event gathering the events are sent to Zuul typically via
webhooks. These types of events will be received in zuul-web that stores them in
Zookeeper. This type of event gathering is used by the Guthub driver. In this
case we can have multiple instances but still receive only one event. So we
don't need to take special care of event deduplication. However it is beneficial
to share the code that pops the events from Zookeeper it won't harm.


Executor via Zookeeper
----------------------

In order to prepare for distributed pipeline execution we need to use Zookeeper
for scheduling jobs on the executors. This is needed so that any scheduler can
take over a pipeline execution without having to restart jobs.

This can be handled similar to node-requests. When a new job needs to be
executed a new sequenced znode with all needed job data is created under the
path ``/zuul/jobs/<tenant>/<sequence>``. In order to receive updates on the job
the scheduler establishes a watch on this. This can also be handled by the
Kazoo TreeCache similar like in nodepool.

An executor will lock this and begin job execution. When it sends job updates
it updates the node data. After job completion it will release the lock. Which
will tell the scheduler to check the result.


Store parsed branch config in Zookeeper
---------------------------------------

Currently the parsed branch config is stored globally but
actually updated during tenant specific reconfigurations. When running multiple
tenants in parallel this might lead to races. So the parsed branch config will
be stored per tenant and thus protected an anyway required lock of a tenant. It
will be stored in the path ``/zuul/tenant/<tenant>/config/<project>/<branch>``.
In case this gets large we could consider storing them compressed.


Store pipeline and tenant state in Zookeeper
--------------------------------------------

The pipeline state is similar to the current status.json. However the frozen
jobs and their state are needed for seemless continuation of the pipeline
execution on a different scheduler. Further this can make it easy to generate
the status.json directly in zuul-web by inspecting the data in Zookeeper. The
pipeline state will be stored in
``/zuul/tenant/<tenant>/pipeline/<pipeline>/queue/<queue>/<buildset uuid>``.

We also need to store tenant state like semaphores in Zookeeper. This will be
stored in ``/zuul/tenant/<tenant>/semaphores/<name>``.

Further also the times database must be stored in Zookeeper. This will be stored
in ``/zuul/tenant/<tenant>/times/<project>/<branch>/<job>``.


Parallelize tenant processing
-----------------------------

Once we have the above data in place we can create the per tenant event and the
global scheduler event queues in Zookeeper. The global scheduler event queue
will receive the trigger, management and result events that are not tenant
specific. The purpose of this queue is to take these events and dispatch them to
the tenant specific queus as appropriate. This event queue can easily processed
using leader election.

Each tenant processor will loop over all tenants that have outstanding events.
Before processing an event it will try to lock the tenant. If it fails it will
continue with the next tenant having outstanding events. If it got the lock it
will process all outstanding events of that tenant and then return the lock.

In order to reduce stalls when doing reconfigurations or tenant reconfigurations
we can easily run more than one tenant processor in a thread pool per scheduler.
This way a tenant that is running a longer reconfiguration won't block other
tenants.


Zuul-web changes
----------------

Now zuul can be changed to directly use the data in Zookeeper instead if
asking the scheduler via gearman.


Security considerations
-----------------------

When switching the executor job queue to Zookeeper we need to take precautions
because this will also contain decrypted secrets. In order to secure this
communication channel we need to make sure that we use authenticated and
encrypted connections to zookeeper.

* There is already a change that adds Zookeeper auth:
  https://review.openstack.org/619156
* Kazoo SSL support just has landed: https://github.com/python-zk/kazoo/pull/513
