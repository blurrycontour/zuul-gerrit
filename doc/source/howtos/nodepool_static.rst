:orphan:

Nodepool - Static
=================

The static driver allows you to use existing compute resources, such as real
hardware or long-lived virtual machines, with nodepool.


Node Requirements
-----------------

Any nodes you setup for nodepool (either real or virtual) must meet
the following requirements:

* Must be reachable by Zuul executors and have SSH access enabled.
* Must have a user that Zuul can use for SSH.
* Must have an Ansible supported Python installed
* Must be reachable by Zuul executors over TCP port 19885 for console
  log streaming.  See :ref:`nodepool_console_streaming`

When setting up your nodepool.yaml file, you will need the host keys
for each node for the ``host-key`` value. This can be obtained with
the command:

.. code-block:: shell

  ssh-keyscan -t ed25519 <HOST>

Nodepool Configuration
----------------------

Below is a sample Nodepool configuration file that sets up static
nodes.  Place this file in ``/etc/nodepool/nodepool.yaml``:

.. code-block:: shell

   sudo bash -c "cat > /etc/nodepool/nodepool.yaml <<EOF
   zookeeper-servers:
     - host: localhost

   labels:
     - name: ubuntu-jammy

   providers:
     - name: static-vms
       driver: static
       pools:
         - name: main
           nodes:
             - name: 192.168.1.10
               labels: ubuntu-jammy
               host-key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGXqY02bdYqg1BcIf2x08zs60rS6XhlBSQ4qE47o5gb"
               username: zuul
             - name: 192.168.1.11
               labels: ubuntu-jammy
               host-key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGXqY02bdYqg1BcIf2x08zs60rS6XhlBSQ5sE47o5gc"
               username: zuul
   EOF"

Make sure that ``username``, ``host-key``, IP addresses and label names are
customized for your environment.

.. _nodepool_console_streaming:

Log streaming
-------------

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

In this situation, , Zuul can be instructed to not to create any spool
files for ``shell`` and ``command`` tasks via setting
``zuul_console_disabled: True`` (usually via a global host variable in
inventory).  Live streaming of ``shell`` and ``command`` calls will of
course be unavailable in this case, but no spool files will be
created.
