:title: Component Overview

Component Overview
==================

.. _components:

Zuul is a distributed system consisting of several components, each of
which is described below.

.. graphviz::
   :align: center

   graph  {
      node [shape=box]
      Database [fontcolor=grey]
      Executor [href="#executor"]
      Finger [href="#finger-gateway"]
      Gearman [shape=ellipse]
      Gerrit [fontcolor=grey]
      Merger [href="#merger"]
      Statsd [shape=ellipse fontcolor=grey]
      Scheduler [href="#scheduler"]
      Zookeeper [shape=ellipse]
      Nodepool
      GitHub [fontcolor=grey]
      Web [href="#web-server"]

      Merger -- Gearman
      Executor -- Statsd
      Executor -- "Job Node"
      Web -- Database
      Web -- Gearman
      Web -- GitHub
      Web -- Zookeeper
      Web -- Executor
      Finger -- Gearman
      Finger -- Executor

      Gearman -- Scheduler;
      Scheduler -- Database;
      Scheduler -- Gerrit;
      Scheduler -- Zookeeper;
      Zookeeper -- Executor;
      Zookeeper -- Finger;
      Zookeeper -- Merger
      Zookeeper -- Nodepool;
      Scheduler -- GitHub;
      Scheduler -- Statsd;
   }

.. contents::
   :depth: 1
   :local:
   :backlinks: none

Each of the Zuul processes may run on the same host, or different
hosts.  Within Zuul, the components communicate with the scheduler via
the Gearman protocol, so each Zuul component needs to be able to
connect to the host running the Gearman server (the scheduler has a
built-in Gearman server which is recommended) on the Gearman port --
TCP port 4730 by default.

The Zuul scheduler communicates with Nodepool via the ZooKeeper
protocol.  Nodepool requires an external ZooKeeper cluster, and the
Zuul scheduler needs to be able to connect to the hosts in that
cluster on TCP port 2181 or 2281.

Both the Nodepool launchers and Zuul executors need to be able to
communicate with the hosts which nodepool provides.  If these are on
private networks, the Executors will need to be able to route traffic
to them.

Only Zuul fingergw and Zuul web need to be publicly accessible;
executors never do. Executors should be accessible on TCP port 7900
by fingergw and web.

A database is required and configured in ``database`` section of
``/etc/zuul/zuul.conf``. Both Zuul scheduler and Zuul web will need
access to it.

If statsd is enabled, the executors and scheduler needs to be able to
emit data to statsd.  Statsd can be configured to run on each host
and forward data, or services may emit to a centralized statsd
collector.  Statsd listens on UDP port 8125 by default.

A minimal Zuul system may consist of a :ref:`scheduler` and
:ref:`executor` both running on the same host.  Larger installations
should consider running multiple executors, each on a dedicated host,
and running mergers on dedicated hosts as well.
