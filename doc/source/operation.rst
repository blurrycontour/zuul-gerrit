:title: Operation

.. _operation:

Operation
=========

You can run any zuul process with the **-f** option to make it not
daemonize and stay in the foreground, logging to your terminal. It's a
good idea at first to check for issues with your configuration.
There's also a **-d** option to engage verbose debug logging, but be
careful in busy deployments as this can generate very large logs.

To start, simply run::

    zuul-scheduler

Before Zuul can run any jobs, it needs to load its configuration, most
of which is in the git repositories that Zuul operates on.  Start an
executor to allow zuul to do that::

    zuul-executor

Zuul should now be able to read its configuration from the configured
repo and process any jobs defined therein.

Scheduler
---------

Operation
~~~~~~~~~

To start the scheduler, run ``zuul-scheduler``.  To stop it, run
``zuul-scheduler stop``.

.. _reconfiguration:

Reconfiguration
~~~~~~~~~~~~~~~

Most of Zuul's configuration is automatically updated as changes to
the repositories which contain it are merged.  However, Zuul must be
explicitly notified of changes to the tenant config file, since it is
not read from a git repository. Zuul supports two kinds of reconfigurations.

The full reconfiguration refetches and reloads the configuration of
all tenants. To do so, run ``zuul-scheduler full-reconfigure``. For
example this can be used to fix eventual configuration inconsistencies
after connection problems with the code hosting system.

To perform the same actions as a full reconfiguration but for a single
tenant, use ``zuul-scheduler tenant-reconfigure TENANT`` (where
``TENANT`` is the name of the tenant to reconfigure).

The smart reconfiguration reloads only the tenants that changed their
configuration in the tenant config file. To do so, run
``zuul-scheduler smart-reconfigure``. In multi tenant systems this can
be much faster than the full reconfiguration so it is recommended to
use the smart reconfiguration after changing the tenant configuration
file.

The ``tenant-reconfigure`` and ``smart-reconfigure`` commands should
only be run on a single scheduler.  Other schedulers will see any
changes to the configuration stored in ZooKeeper and automatically
update their configuration in the background without interrupting
processing.

Merger
------

Operation
~~~~~~~~~

To start the merger, run ``zuul-merger``.

In order to stop the merger and under normal circumstances it is
best to pause and wait for all currently running tasks to finish
before stopping it. To do so run ``zuul-merger pause``.

To stop the merger, run ``zuul-merger stop``. This will wait for any
currently running merge task to complete before exiting. As a result
this is always a graceful way to stop the merger.
``zuul-merger graceful`` is an alias for ``zuul-merger stop`` to make
this consistent with the executor.

Executor
--------

Operation
~~~~~~~~~

To start the executor, run ``zuul-executor``.

There are several commands which can be run to control the executor's
behavior once it is running.

To pause the executor and prevent it from running new jobs you can
run ``zuul-executor pause``.

To cause the executor to stop accepting new jobs and exit when all running
jobs have finished you can run ``zuul-executor graceful``. Under most
circumstances this will be the best way to stop Zuul.

To stop the executor immediately, run ``zuul-executor stop``. Jobs that were
running on the stopped executor will be rescheduled on other executors.

The executor normally responds to a ``SIGTERM`` signal in the same way
as the ``graceful`` command, however you can change this behavior to match
``stop`` with the :attr:`executor.sigterm_method` setting.

To enable or disable running Ansible in verbose mode (with the
``-vvv`` argument to ansible-playbook) run ``zuul-executor verbose``
and ``zuul-executor unverbose``.

.. _ansible-and-python-3:

Ansible and Python 3
~~~~~~~~~~~~~~~~~~~~

As noted above, the executor runs Ansible playbooks against the remote
node(s) allocated for the job.  Since part of executing playbooks on
remote hosts is running Python scripts on them, Ansible needs to know
what Python interpreter to use on the remote host.  With older
distributions, ``/usr/bin/python2`` was a generally sensible choice.
However, over time a heterogeneous Python ecosystem has evolved where
older distributions may only provide Python 2, most provide a mixed
2/3 environment and newer distributions may only provide Python 3 (and
then others like RHEL8 may even have separate "system" Python versions
to add to confusion!).

Ansible's ``ansible_python_interpreter`` variable configures the path
to the remote Python interpreter to use during playbook execution.
This value is set by Zuul from the ``python-path`` specified for the
node by Nodepool; see the `nodepool configuration documentation
<https://zuul-ci.org/docs/nodepool/configuration.html>`__.

This defaults to ``auto``, where Ansible will automatically discover
the interpreter available on the remote host.  However, this setting
only became available in Ansible >=2.8, so Zuul will translate
``auto`` into the old default of ``/usr/bin/python2`` when configured
to use older Ansible versions.

Thus for modern Python 3-only hosts no further configuration is needed
when using Ansible >=2.8 (e.g. Fedora, Bionic onwards).  If using
earlier Ansible versions you may need to explicitly set the
``python-path`` if ``/usr/bin/python2`` is not available on the node.

Ansible roles/modules which include Python code are generally Python 3
safe now, but there is still a small possibility of incompatibility.
See also the Ansible `Python 3 support page
<https://docs.ansible.com/ansible/latest/reference_appendices/python_3_support.html>`__.

.. _nodepool_console_streaming:

Log streaming
~~~~~~~~~~~~~

The log streaming service enables Zuul to show the live status of
long-running ``shell`` or ``command`` tasks.  The server side is setup
by the ``zuul_console:`` task built-in to Zuul's Ansible installation.
The executor requires the ability to communicate with this server on
the job nodes via port ``19885`` for this to work.

The log streaming service spools command output via files on the job
node in the format ``/tmp/console-<uuid>-<task_id>-<host>.log``.  By
default, it will clean these files up automatically.

Occasionally, a streaming file may be left if a job is interrupted.
These may be safely removed after a short period of inactivity with a
command such as

.. code-block:: shell

   find /tmp -maxdepth 1 -name 'console-*-*-<host>.log' -mtime +2 -delete

If the executor is unable to reach port ``19885`` (for example due to
firewall rules), or the ``zuul_console`` daemon can not be run for
some other reason, the command to clean these spool files will not be
processed and they may be left behind; on an ephemeral node this is
not usually a problem, but on a static node these files will persist.

In this situation, Zuul can be instructed to not to create any spool
files for ``shell`` and ``command`` tasks via setting
``zuul_console_disabled: True`` (usually via a global host variable in
inventory).  Live streaming of ``shell`` and ``command`` calls will of
course be unavailable in this case, but no spool files will be
created.

For Kubernetes-based job nodes the connection from the executor to the
``zuul_console`` daemon is established by using ``kubectl port-forward``
to forward a local port to the appropriate port on the pod containing
the job node.  If the Kubernetes user is not bound to a role that has
authorization for port-forwarding, this will prevent connection to
the ``zuul_console`` daemon.

Web Server
----------

Operation
~~~~~~~~~

To start the web server, run ``zuul-web``.  To stop it, kill the
PID which was saved in the pidfile specified in the configuration.

Finger Gateway
--------------


Operation
~~~~~~~~~

To start the finger gateway, run ``zuul-fingergw``.  To stop it, kill the
PID which was saved in the pidfile specified in the configuration.
