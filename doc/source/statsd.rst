:title: Statsd reporting

Statsd reporting
================

Zuul comes with support for the statsd protocol, when enabled and configured
(see below), the Zuul scheduler will emit raw metrics to a Statsd receiver
which let you in turn generate nice graphics. An example is OpenStack Zuul
status page: http://status.openstack.org/zuul/

Configuration
-------------

You will need the statsd python module installed which is already a dependency
when installing via pip. If the module is missing though, it will not prevent
Zuul from proceeding.

The configuration is done via environnement variables STATSD_HOST and
STATSD_PORT. They are interpreted by the statsd module directly and there is no
such paremeter in zuul.conf yet. Your init script will have to initialize both
of them before launching Zuul.

Your init script most probably a shell file named /etc/default/zuul which would
contain the environnement variables::

  $ cat /etc/default/zuul
  STATSD_HOST=10.0.0.1
  STATSD_PORT=8125

Metrics
-------

The metrics are emitted by Zuul scheduler (`zuul/scheduler.py`):

**gerrit.events.<type> (counters)**
  Gerrit emits different kind of message over its `stream-events` interface.
  Each message is defined by a type which is defined by Gerrit. A non
  exhaustive lists of events is:

    * patchset-created
    * draft-published
    * change-abandonned
    * change-restored
    * change-merged
    * merge-failed
    * comment-added
    * ref-updated
    * reviewer-added

  Refer to your Gerrit installation documentation for an exhaustive list.

**zuul.pipeline.***
  Holds metrics specific to jobs. The hierarchy is:

    #. **<pipeline name>** as defined in your `layout.yaml` file (ex: `gate`,
                         `test`, `publish`). It contains:

      #. **all_jobs** counter of jobs triggered by the pipeline.
      #. **current_changes** A gauge for the number of Gerrit changes being
               proceeded by this pipeline.
      #. **job** subtree detailing per jobs statistics:

        #. **<jobname>** The triggered job name.
        #. **<build result>** Result as defined in your triggering system. For
                 Jenkins that would be SUCCESS, FAILURE, UNSTABLE, LOST.  The
                 metrics holds both an increasing counter and a timing reporting
                 the duration of the build. Whenever the result is a SUCCESS or
                 FAILURE, Zuul will additionally report the duration of the
                 build as a timing event.

      #. **resident_time** timing representing how long the Change has been
               known by Zuul (which includes build time and Zuul overhead).
      #. **total_changes** counter of the number of change proceeding since
               Zuul started.

  Additionally, the `zuul.pipeline.<pipeline name>` hierarchy contains
  `current_changes` and `resident_time` metrics for each projects. The slash
  separator used in Gerrit name being replaced by dots.

  As an example, given a job named `myjob` triggered by the `gate` pipeline
  which took 40 seconds to build, the Zuul scheduler will emit the following
  statsd events:

    * `zuul.pipeline.gate.job.myjob.SUCCESS` +1
    * `zuul.pipeline.gate.job.myjob`  40 seconds
    * `zuul.pipeline.gate.all_jobs` +1
