Zuul Internals
==============

While most people should not need to understand the details of Zuul's internal
data model, understanding the data model is essential people people writing
code for Zuul, and might be interesting to advanced users. The model is
defined in `zuul/model.py`_.

.. _zuul/model.py: http://git.openstack.org/cgit/openstack-infra/zuul/tree/zuul/model.py

Data Model
----------

It all starts with the :py:class:`~zuul.model.Pipeline`. A Pipeline is the
basic organizational structure that everything else hangs off.

.. autoclass:: zuul.model.Pipeline

Pipelines have a configured
:py:class:`Manager <zuul.manager.BasePipelineManager>` which controlls how
the :py:class:`Change <zuul.model.Changeish>` objects are enqueued and
processed.

There are currently two, 
:py:class:`~zuul.manager.dependent.DependentPipelineManager` and
:py:class:`~zuul.manager.independent.IndependentPipelineManager`

.. autoclass:: zuul.manager.BasePipelineManager
.. autoclass:: zuul.manager.dependent.DependentPipelineManager
.. autoclass:: zuul.manager.independent.IndependentPipelineManager

A :py:class:`~zuul.model.Pipeline` has one or more
:py:class:`~zuul.model.ChangeQueue`.

.. autoclass:: zuul.model.ChangeQueue

A :py:class:`~zuul.model.Job` represents the definition of what to do. A
:py:class:`~zuul.model.Build` represents a single run of a
:py:class:`~zuul.model.Job`. A :py:class:`~zuul.model.JobTree` is used to
encapsulate the dependencies between one or more :py:class:`~zuul.model.Job`
objects.

.. autoclass:: zuul.model.Job
.. autoclass:: zuul.model.JobTree
.. autoclass:: zuul.model.Build

The :py:class:`~zuul.manager.base.PipelineManager` enqueues each
:py:class:`Change <zuul.model.Changeish>` into the
:py:class:`~zuul.model.ChangeQueue` in a :py:class:`~zuul.model.QueueItem`.

.. autoclass:: zuul.model.QueueItem

As the Changes are processed, each :py:class:`~zuul.model.Build` is put into
a :py:class:`~zuul.model.BuildSet`

.. autoclass:: zuul.model.BuildSet

Changes
~~~~~~~

.. autoclass:: zuul.model.Changeish
.. autoclass:: zuul.model.Change
.. autoclass:: zuul.model.Ref

Filters
~~~~~~~

.. autoclass:: zuul.model.ChangeishFilter
.. autoclass:: zuul.model.EventFilter


Tenants
~~~~~~~

An abide is a collection of tenants.

.. autoclass:: zuul.model.UnparsedAbideConfig
.. autoclass:: zuul.model.UnparsedTenantConfig

Other Global Objects
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: zuul.model.Project
.. autoclass:: zuul.model.Layout
.. autoclass:: zuul.model.RepoFiles
.. autoclass:: zuul.model.Worker
.. autoclass:: zuul.model.TriggerEvent


Nearest Non Failing Change Example
----------------------------------

The following is a walkthrough of actions in a Pipeline managed by the
DependentPipelineManager as part of the Nearest Non-Failing Change algorithm
written in terms of objects in the data model.
