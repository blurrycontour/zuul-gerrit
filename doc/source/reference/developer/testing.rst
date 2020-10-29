Testing
=======

Zuul provides an extensive framework for performing functional testing
on the system from end-to-end with major external components replaced
by fakes for ease of use and speed.

Test classes that subclass :py:class:`~zuul.tests.base.ZuulTestCase` have
access to a number of attributes useful for manipulating or inspecting
the environment being simulated in the test:

.. autofunction:: zuul.tests.base.simple_layout

.. autoclass:: zuul.tests.base.ZuulTestCase
   :members:

.. autoclass:: zuul.tests.base.FakeGerritConnection
   :members:
   :inherited-members:

.. autoclass:: zuul.tests.base.FakeGearmanServer
   :members:

.. autoclass:: zuul.tests.base.RecordingExecutorServer
   :members:

.. autoclass:: zuul.tests.base.FakeBuild
   :members:

.. autoclass:: zuul.tests.base.BuildHistory
   :members:
