Zookeeper Map
=============

This is a reference for object layout in Zookeeper.

.. path:: zuul

   All ephemeral data stored here.  Remove the entire tree to "reset"
   the system.

.. path:: zuul/cache/connection/<connection>

   The connection cache root.  Each connection has a dedicated space
   for its caches.  Two types of caches are currently implemented:
   change and branch.

.. path:: zuul/cache/connection/<connection>/branches

   The connection branch cache root.  Contains the cache itself and a
   lock.

.. path:: zuul/cache/connection/<connection>/branches/data
   :type: BranchCacheZKObject (sharded)

   The connection branch cache data.  This is a single sharded JSON blob.

.. path:: zuul/cache/connection/<connection>/branches/lock
   :type: RWLock

   The connection branch cache read/write lock.

.. path:: zuul/cache/connection/<connection>/cache

   The connection change cache.  Each node under this node is an entry
   in the change cache.  The node ID is a sha256 of the cache key, the
   contents are the JSON serialization of the cache entry metadata.
   One of the included items is the `data_uuid` which is used to
   retrieve the actual change data.

   When a cache entry is updated, a new data node is created without
   deleting the old data node.  They are eventually garbage collected.

.. path:: zuul/cache/connection/<connection>/data

   Data for the change cache.  These nodes are identified by a UUID
   referenced from the cache entries.

   These are sharded JSON blobs of the change data.

.. path:: zuul/cleanup

   This node holds locks for the cleanup routines to make sure that
   only one scheduler runs them at a time.

   .. path:: build_requests
   .. path:: connection
   .. path:: general
   .. path:: merge_requests
   .. path:: node_request
   .. path:: sempahores

.. path:: zuul/components

   The component registry.  Each Zuul process registers itself under
   the appropriate node in this hierarchy so the system has a holistic
   view of what's running.  The name of the node is based on the
   hostname but is a sequence node in order to handle multiple
   processes.  The nodes are ephemeral so an outage is automatically
   detected.

   The contents of each node contain information about the running
   process and may be updated periodically.

   .. path:: executor
   .. path:: fingergw
   .. path:: merger
   .. path:: scheduler
   .. path:: web

.. path:: zuul/config/cache

   The unparsed config cache.  This contains the contents of every
   Zuul config file returned by the mergers for use in configuration.
   Organized by repo canonical name, branch, and filename.  The files
   themeselves are sharded.

.. path:: zuul/config/lock

   Locks for the unparsed config cache.

.. path:: zuul/events/connection/<connection>/events
   :type: ConnectionEventQueue

   The connection event queue root.  Each connection has an event
   queue where incoming events are recorded before being moved to the
   tenant event queue.

.. path:: zuul/events/connection/<connection>/events/queue

   The actual event queue.  Entries in the queue reference separate
   data nodes.  These are sequence nodes to maintain the event order.

.. path:: zuul/events/connection/<connection>/events/data

   Event data nodes referenced by queue items.  These are sharded.

.. path:: zuul/events/connection/<connection>/events/election

   An election to determine which scheduler processes the event queue
   and moves events to the tenant event queues.

   Drivers may have additional elections as well.  For example, Gerrit
   has an election for the watcher and poller.

.. path:: zuul/events/tenant/<tenant>

   Tenant-specific event queues.  Each queue described below has a
   data and queue subnode.

.. path:: zuul/events/tenant/<tenant>/management

   The tenant-specific management event queue.

.. path:: zuul/events/tenant/<tenant>/trigger

   The tenant-specific trigger event queue.

.. path:: zuul/events/tenant/<tenant>/pipelines

   Holds a set of queues for each pipeline.

.. path:: zuul/events/tenant/<tenant>/pipelines/<pipeline>/management

   The pipeline management event queue.

.. path:: zuul/events/tenant/<tenant>/pipelines/<pipeline>/result

   The pipeline result event queue.

.. path:: zuul/events/tenant/<tenant>/pipelines/<pipeline>/trigger

   The pipeline trigger event queue.

.. path:: zuul/executor/unzoned
   :type: JobRequestQueue

   The unzoned executor build request queue.  The generic description
   of a job request queue follows:

   .. path:: requests/<request uuid>

      Requests are added by UUID.  Consumers watch the entire tree and
      order the requests by znode creation time.

   .. path:: locks/<request uuid>
      :type: Lock

      A consumer will create a lock under this node before processing
      a request.  The znode containing the lock and the requent znode
      have the same UUID.  This is a side-channel lock so that the
      lock can be held while the request itself is deleted.

   .. path:: params/<request uuid>

      Parameters can be quite large, so they are kept in a separate
      znode and only read when needed, and may be removed during
      request processing to save space in ZooKeeper.  The data may be
      sharded.

   .. path:: result-data/<request uuid>

      When a job is complete, the results of the merge are written
      here.  The results may be quite large, so they are sharded.

   .. path:: results/<request uuid>

      Since writing sharded data is not atomic, once the results are
      written to ``result-data``, a small znode is written here to
      indicate the results are ready to read.  The submitter can watch
      this znode to be notified that it is ready.

   .. path:: waiters/<request uuid>
      :ephemeral:

      A submitter who requires the results of the job creates an
      ephemeral node here to indicate their interest in the results.
      This is used by the cleanup routines to ensure that they don't
      prematurely delete the result data.  Used for merge jobs

.. path:: zuul/executor/zones/<zone>

   A zone-specific executor build request queue.  The contents are the
   same as above.

.. path:: zuul/layout/<tenant>

   The layout state for the tenant.  Contains the cache and time data
   needed for a component to determine if its in-memory layout is out
   of date and update it if so.

.. path:: zuul/locks

   Holds various types of locks so that multiple components can coordinate.

.. path:: zuul/locks/events

   Locks related to tenant event queues.

.. path:: zuul/locks/events/trigger/<tenant>
   :type: Lock

   The scheduler locks the trigger event queue for each tenant before
   processing it.  This lock is only needed when processing and
   removing items from the queue; no lock is required to add items.

.. path:: zuul/locks/events/management/<tenant>
   :type: Lock

   The scheduler locks the management event queue for each tenant
   before processing it.  This lock is only needed when processing and
   removing items from the queue; no lock is required to add items.

.. path:: zuul/locks/pipeline

   Locks related to pipelines.

.. path:: zuul/locks/pipeline/<tenant>/<pipeline>
   :type: Lock

   The scheduler obtains a lock before processing each pipeline.

.. path:: zuul/locks/tenant

   Tenant configuration locks.

.. path:: zuul/locks/tenant/<tenant>
   :type: RWLock

   A write lock is obtained at this location before creating a new
   tenant layout and storing its metadata in ZooKeeper.  Components
   which later determine that they need to update their tenant
   configuration to match the state in ZooKeeper will obtain a read
   lock at this location to ensure the state isn't mutated again while
   the components are updating their layout to match.

.. path:: zuul/ltime

   An empty node which serves to coordinate logical timestamps across
   the cluster.  Components may update this znode which will cause the
   latest ZooKeeper transaction ID to appear in the zstat for this
   znode.  This is known as the `ltime` and can be used to communicate
   that any subsequent transactions have occurred after this `ltime`.
   This is frequently used for cache validation.  Any cache which was
   updated after a specified `ltime` may be determined to be
   sufficiently up-to-date for use without invalidation.

.. path:: zuul/merger
   :type: JobRequestQueue

   A JobRequestQueue for mergers.  See :path:`zuul/executor/unzoned`.

.. path:: zuul/nodepool
   :type: NodepoolEventElection

   An election to decide which scheduler will monitor nodepool
   requests and generate node completion events as they are completed.

.. path:: zuul/results/management

   Stores results from management events (such as an enqueue event).

.. path:: zuul/scheduler/timer-election
   :type: SessionAwareElection

   An election to decide which scheduler will generate events for
   timer pipeline triggers.

.. path:: zuul/scheduler/stats-election
   :type: SchedulerStatsElection

   An election to decide which scheduler will report system-wide stats
   (such as total node requests).

.. path:: zuul/semaphores/<tenant>/<semaphore>
   :type: SemaphoreHandler

   Represents a semaphore.  Information about which builds hold the
   semaphore is stored in the znode data.

.. path:: zuul/system
   :type: SystemConfigCache

   System-wide configuration data.

   .. path:: conf

      The serialized version of the unparsed abide configuration as
      well as system attributes (such as the tenant list).

   .. path:: conf-lock
      :type: WriteLock

      A lock to be acquired before updating :path:`zuul/system/conf`

.. path:: zuul/tenant/<tenant>

   Tenant-specific information here.

.. path:: zuul/tenant/<tenant>/pipeline/<pipeline>

   Pipeline state.

.. path:: zuul/tenant/<tenant>/pipeline/<pipeline>/queue

   Holds queue objects.

.. path:: zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>

   Items belong to queues, but are held in their own hierarchy since
   they may shift to differrent queues during reconfiguration.

.. path:: zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>

   There will only be one buildset under the buildset/ node.  If we
   reset it, we will get a new uuid and delete the old one.  Any
   external references to it will be automatically invalidated.

.. path:: zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>/repo_state

   The global repo state for the buildset is kept in its own node
   since it can be large, and is also common for all jobs in this
   buildset.

.. path:: zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>/job/<job name>

   The frozen job.

.. path:: zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>/job/<job name>/build/<build uuid>

   Information about this build of the job.  Similar to buildset,
   there should only be one entry, and using the UUID automatically
   invalidates any references.

.. path:: zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>/job/<job name>/build/<build uuid>/parameters

   Parameters for the build; these can be large so they're in their
   own znode and will be read only if needed.
