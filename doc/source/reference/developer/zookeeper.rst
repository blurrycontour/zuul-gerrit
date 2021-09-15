Zookeeper Map
=============

This is a reference for object layout in Zookeeper.

/zuul
-----

All ephemeral data stored here.  Remove the entire tree to "reset" the
system.

/zuul/tenant/<tenant>
---------------------

Tenant-specific information here.

/zuul/tenant/<tenant>/pipeline/<pipeline>
-----------------------------------------

Pipeline state.

/zuul/tenant/<tenant>/pipeline/<pipeline>/queue/<queue>
-------------------------------------------------------

Holds queue objects.

/zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>
----------------------------------------------------------

Items belong to queues, but are held in their own hierarchy since they
may shift to differrent queues during reconfiguration.

/zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>
-----------------------------------------------------------------------------------

There will only be one buildset uinder the buildset/ node.  If we
reset it, we will get a new uuid and delete the old one.  Any external
references to it will be automatically invalidated.

/zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>/repo_state
----------------------------------------------------------------------------------------------

The global repo state for the buildset is kept in its own node since
it can be large, and is also common for all jobs in this buildset.

/zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>/job/<job name>
--------------------------------------------------------------------------------------------------

The frozen job.

/zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>/job/<job name>/build/<build uuid>
---------------------------------------------------------------------------------------------------------------------

Information about this build of the job.  Similar to buildset, there
should only be one entry, and using the UUID automatically invalidates
any references.

/zuul/tenant/<tenant>/pipeline/<pipeline>/item/<item uuid>/buildset/<buildset uuid>/job/<job name>/build/<build uuid>/parameters
--------------------------------------------------------------------------------------------------------------------------------

Parameters for the build; these can be large so they're in their own
znode and will be read only if needed.
