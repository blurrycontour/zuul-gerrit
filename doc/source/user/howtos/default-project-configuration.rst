:title: Default project configuration

Default project configuration
=============================

Zuul does not report errors to project without pipelines. To assist
new project creation, it is recommended to enable this project
configuration (assuming the check pipeline is named *check*).

.. code-block:: yaml

  # org-config/zuul.d/projects.yaml
  - project:
      name: "^.*$"
      check:
        jobs: []


Like that, when a project submit its initial zuul.yaml file, errors will be
reported to the code review system. The name regexp can be adapted to
preventing reporting error to third party system.
