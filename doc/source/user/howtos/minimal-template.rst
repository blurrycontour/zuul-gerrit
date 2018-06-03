:title: Minimal template

.. _pti:

Minimal template
================

Zuul does not report errors to project without pipelines. To assist
new project creation, it is recommended to always enable this template:

.. code-block:: yaml

  # org-config/zuul.d/templates.yaml
  - project-template:
    name: system-required
    description: |
      Jobs that *every* project in OpenStack CI should have by default.
    merge-check:
      jobs:
        - noop

Like that, when a project submit its initial zuul.yaml file, then errors will be
reported to the code review system.
