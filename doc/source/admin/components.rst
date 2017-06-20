Components
==========

Zuul is a distributed system consisting of several components, each of
which is described below.  All Zuul processes read the
**/etc/zuul.conf** file (an alternate location may be supplied on the
command line) which uses an INI file syntax.  Each component may have
its own configuration file, though you may find it simpler to use the
same file for all components.

A minimal Zuul system may consist of a *scheduler* and *executor* both
running on the same host.  Larger installations should consider
running multiple executors, each on a dedicated host, and running
mergers on dedicated hosts as well.

Common
------

The following applies to all Zuul components.

Configuration
~~~~~~~~~~~~~

The following sections of **zuul.conf** are used by all Zuul components:

gearman
"""""""

Client connection information for gearman.

**server**
  Hostname or IP address of the Gearman server.
  ``server=gearman.example.com`` (required)

**port**
  Port on which the Gearman server is listening.
  ``port=4730`` (optional)

**ssl_ca**
  Optional: An openssl file containing a set of concatenated
  “certification authority” certificates in PEM formet.

**ssl_cert**
  Optional: An openssl file containing the client public certificate in
  PEM format.

**ssl_key**
  Optional: An openssl file containing the client private key in PEM format.


Scheduler
---------

The scheduler is the primary component of Zuul.  The scheduler is not
a scalable component; one, and only one, scheduler must be running at
all times for Zuul to be operational.  It receives events from any
connections to remote systems which have been configured, enqueues
items into pipelines, distributes jobs to executors, and reports
results.

Configuration
~~~~~~~~~~~~~

The following sections of **zuul.conf** are used by the scheduler:

gearman_server
""""""""""""""

The builtin gearman server. Zuul can fork a gearman process from itself rather
than connecting to an external one.

**start**
  Whether to start the internal Gearman server (default: False).
  ``start=true``

**listen_address**
  IP address or domain name on which to listen (default: all addresses).
  ``listen_address=127.0.0.1``

**log_config**
  Path to log config file for internal Gearman server.
  ``log_config=/etc/zuul/gearman-logging.yaml``

**ssl_ca**
  Optional: An openssl file containing a set of concatenated “certification authority” certificates
  in PEM formet.

**ssl_cert**
  Optional: An openssl file containing the server public certificate in PEM format.

**ssl_key**
  Optional: An openssl file containing the server private key in PEM format.

webapp
""""""

**listen_address**
  IP address or domain name on which to listen (default: 0.0.0.0).
  ``listen_address=127.0.0.1``

**port**
  Port on which the webapp is listening (default: 8001).
  ``port=8008``

.. TODO: move this to webapp (currently in 'zuul')

**status_expiry**
  Zuul will cache the status.json file for this many seconds. This is an
  optional value and ``1`` is used by default.
  ``status_expiry=1``

scheduler
"""""""""
.. TODO: rename this to 'scheduler' (currently 'zuul') and update to match these docs

**tenant_config**
  Path to tenant config file.
  ``layout_config=/etc/zuul/tenant.yaml``

**log_config**
  Path to log config file.
  ``log_config=/etc/zuul/scheduler-logging.yaml``

**pidfile**
  Path to PID lock file.
  ``pidfile=/var/run/zuul/scheduler.pid``

**state_dir**
  Path to directory that Zuul should save state to.
  ``state_dir=/var/lib/zuul``

Operation
~~~~~~~~~

To start the scheduler, run ``zuul-scheduler``.  To stop it, kill the
PID which was saved in the pidfile specified in the configuration.

Most of Zuul's configuration is automatically updated as changes to
the repositories which contain it are merged.  However, Zuul must be
explicitly notified of changes to the tenant config file, since it is
not read from a git repository.  To do so, send the scheduler PID
(saved in the pidfile specified in the configuration) a SIGHUP signal.

Merger
------

Mergers are an optional Zuul service; they are not required for Zuul
to operate, but some high volume sites may benefit from running them.
Zuul performs quite a lot of git operations in the course of its work.
Each change that is to be tested must be speculatively merged with the
current state of its target branch to ensure that it can merge, and to
ensure that the tests that Zuul perform accurately represent the
outcome of merging the change.  Because Zuul's configuration is stored
in the git repos it interacts with, and is dynamically evaluated, Zuul
often needs to perform a speculative merge in order to determine
whether it needs to perform any further actions.

All of these git operations add up, and while Zuul executors can also
perform them, large numbers may impact their ability to run jobs.
Therefore, administrators may wish to run standalone mergers in order
to reduce the load on executors.

Configuration
~~~~~~~~~~~~~

Operation
~~~~~~~~~

