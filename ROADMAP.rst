Current and Future Zuul v3 Work
===============================

Zuul v3 has a tight immediate focus on getting it out the door and running
for its first users. That means there is an immediate set of priorities that
take priority over everything else.

There is also a large set of things that we all want to do. Some of them have
components that need current attention even though they are not in service
of the immediate priorities. Some of them are being deliberately deferred
until later, even as far as discussion is concerned.

Below is a list of the immediate priorities as well as the larger list of
big items with annotations about what's in-scope currently and what's deferred
til later on purpose.

Immediate Priorities
--------------------

* Begin using Zuul v3 to run jobs for Zuul itself (done)
* Implement Github support
* Align BonnyCI to no longer be running a fork
* Move OpenStack Infra to use Zuul v3
* Document use and operation
* Begin using Zuul v3 to run tests on Ansible repos

Currently In-scope Lower Priority
---------------------------------

* Define Nodepool Provider Plugin Interface
* Implement Static Node support for Nodepool

Current and Future
------------------

What follows is a list of things we know about. It's neither exclusive or
exhaustive, nor does being listed here mean a thing is absolutely going to
happen. It's a list of things we know about, and whether they're a now or a
future thing.

Zuul Plugins
~~~~~~~~~~~~

In-scope:

* Plugin Interface (done)
* GitHub Plugin

For Later:

* FedMsg Plugin
* MQTT Plugin
* Pagure Plugin
* Gitlab Plugin
* Bitbucket Plugin

Ansible Integration
~~~~~~~~~~~~~~~~~~~

In-scope:

* Define test jobs to verify PRs to Ansible won't break Zuul

For Later:

* Upstream local forked command module
* Discuss options upstream for supporting streaming logs
* Discuss options upstream for supporting restricted module set

Shared Jobs
~~~~~~~~~~~

In-scope:

* How much do we share content between zuuls?
* What sort of contract can users expect from jobs?

Dashboard
~~~~~~~~~

In-scope:

* What HTTP/REST technology should we use?

For Later:

* Should a Dashboard be Required or Optional?

Log streaming
~~~~~~~~~~~~~

In-scope:

* Write a websocket streamer
* Write a global gateway for finger log streamers

For later:

* Add job listing to finger? Other things?

Scale-out Ingestors
~~~~~~~~~~~~~~~~~~~

For Later:

* Event queueing/de-dup technology
* Agree on design

Authenticated RPC
~~~~~~~~~~~~~~~~~

For Later:

* Do we ever want this?
* Per-tenant filtered status.json?
* Use REST and/or gRPC?
* What auth design/approach should be taken?

Pluggable Nodepool Providers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In-scope:

* General Plugin API
* Static Node Support

For Later:

* OCI Plugin
* Docker Swarm Plugin
* Kubernetes Plugin
* Mesos Plugin
* Linch-pin Plugin vs. Direct plugins
* Heat plugin

Multi-node Node Provider plugins
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For Now:

* Will we block future support if we don't consider this in the Provider
  Plugin API design?

For Later:

* What does it look like for a provider to return multiple nodes?

Kubernetes Native Workloads
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For Later:

* How does git repo state transfer work?

Running Zuul in Kubernetes
~~~~~~~~~~~~~~~~~~~~~~~~~~

In-scope:

* Where should we put existing Dockerfiles/compose files/helm charts for folks
  to collaborate?

For Later:

* Is anything fundamental missing from Zuul or blocking this?
* How much can/should a zuul running in kubernetes leverage it for subprocess
  management?

Prometheus-style Status Endpoints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For Later:

* Do we want to directly support this?
* Do we need one per process or can we bundle?
* How much of the statsd reporting do we try to duplicate?
