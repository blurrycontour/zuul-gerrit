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
:py:class:`~zuul.manager.base.PipelineManager` which controlls how
the :py:class:`Change <zuul.model.Changeish>` objects are enqueued and
processed.

There are currently two, 
:py:class:`~zuul.manager.dependent.DependentPipelineManager` and
:py:class:`~zuul.manager.independent.IndependentPipelineManager`

.. autoclass:: zuul.manager.base.PipelineManager
.. autoclass:: zuul.manager.dependent.DependentPipelineManager
.. autoclass:: zuul.manager.independent.IndependentPipelineManager

Nearest Non Failing Change Example
----------------------------------

The following is a walkthrough of actions in a Pipeline managed by the
DependentPipelineManager as part of the Nearest Non-Failing Change algorithm
written in terms of objects in the data model.
