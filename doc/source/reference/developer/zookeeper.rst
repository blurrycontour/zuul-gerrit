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

.. path:: zuul/events/connection/<connection>

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

   The unzoned executor build request queue.  The generic description
   of a job request queue follows:

   .. path:: locks

      Executors or mergers hold ephemeral locks on requests via nodes
      here.

   .. path:: params

      Request parameters are offloaded to sharded nodes here because
      they can be quite large.

   .. path:: requests

      The actual requests.  Identified by build or merge job UUID.
      The queue order is determined by creation time and precedence.

   .. path:: result-data

      Offloaded result data, once a request is complete.

   .. path:: results

      A pointer to the result-data.

   .. path:: waiters

      If a component wants to wait for results, it registers its
      interest here with an ephemeral node so schedulers can determine
      when it is safe to delete result data.  Used for merge jobs.

.. path:: zuul/executor/zones/<zone>

   A zone-specific executor build request queue.  The contents are the
   same as above.

.. path:: zuul/layout/<tenant>

   The layout state for the tenant.  Contains the cache and time data
   needed for a component to determine if its in-memory layout is out
   of date and update it if so.

.. path:: zuul/locks
.. path:: zuul/ltime
.. path:: zuul/merger
.. path:: zuul/nodepool
.. path:: zuul/results
.. path:: zuul/scheduler
.. path:: zuul/semaphores
.. path:: zuul/system

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

   There will only be one buildset uinder the buildset/ node.  If we
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
