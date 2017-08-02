:title: Tenant Configuration

.. _tenant-config:

Tenant Configuration
====================

After *zuul.conf* is configured, Zuul component servers will be able
to start, but a tenant configuration is required in order for Zuul to
perform any actions.  The tenant configuration file specifies upon
which projects Zuul should operate.  These repositories are
grouped into tenants.  The configuration of each tenant is separate
from the rest (no pipelines, jobs, etc are shared between them).

A project may appear in more than one tenant; this may be useful if
you wish to use common job definitions across multiple tenants.

The tenant configuration file is specified by the *tenant_config*
setting in the *scheduler* section of *zuul.yaml*.  It is a YAML file
which, like other Zuul configuration files, is a list of configuration
objects, though only one type of object is supported, *tenant*.

Tenant
------

A tenant is a collection of projects which share a Zuul
configuration.  An example tenant definition is::

  - tenant:
      name: my-tenant
      max-nodes-per-job: 5
      exclude-unprotected-branches: false
      source:
        gerrit:
          config-projects:
            - common-config
            - shared-jobs:
                include: job
          untrusted-projects:
            - zuul-jobs:
                shadow: common-config
            - project1
            - project2:
                exclude-unprotected-branches: true

The following attributes are supported:

**name** (required)
  The name of the tenant.  This may appear in URLs, paths, and
  monitoring fields, and so should be restricted to URL friendly
  characters (ASCII letters, numbers, hyphen and underscore) and you
  should avoid changing it unless necessary.

**max-nodes-per-job** (optional)
  The maximum number of nodes a job can request, default to 5.
  A '-1' value removes the limit.

**exclude-unprotected-branches** (optional)
  When using a branch and pull model on a shared github repository there are
  usually one or more protected branches which are gated and a dynamic number of
  personal/feature branches which are the source for the pull requests. These
  branches can potentially include broken zuul config and therefore break the
  global tenant wide configuration. In order to deal with this zuul's operations
  can be limited to the protected branches which are gated. This is a tenant
  wide setting and can be overridden per project. If not specified, defaults
  to ``false``.

**source** (required)
  A dictionary of sources to consult for projects.  A tenant may
  contain projects from multiple sources; each of those sources must
  be listed here, along with the projects it supports.  The name of a
  :ref:`connection<connections>` is used as the dictionary key
  (e.g. `gerrit` in the example above), and the value is a further
  dictionary containing the keys below.

  **config-projects**
    A list of projects to be treated as config projects in this
    tenant.  The jobs in a config project are trusted, which means
    they run with extra privileges, do not have their configuration
    dynamically loaded for proposed changes, and zuul.yaml files are
    only searched for in the master branch.

  **untrusted-projects**
    A list of projects to be treated as untrusted in this tenant.  An
    untrusted project is the typical project operated on by Zuul.
    Their jobs run in a more restrictive environment, they may not
    define pipelines, their configuration dynamically changes in
    response to proposed changes, Zuul will read configuration files
    in all of their branches.

  Each of the projects listed may be either a simple string value, or
  it may be a dictionary with the following keys:

    **include**
    Normally Zuul will load all of the configuration classes
    appropriate for the type of project (config or untrusted) in
    question.  However, if you only want to load some items, the
    *include* attribute can be used to specify that *only* the
    specified classes should be loaded.  Supplied as a string, or a
    list of strings.

    **exclude**
    A list of configuration classes that should not be loaded.

    **shadow**
    A list of projects which this project is permitted to shadow.
    Normally, only one project in Zuul may contain definitions for a
    given job.  If a project earlier in the configuration defines a
    job which a later project redefines, the later definition is
    considered an error and is not permitted.  The "shadow" attribute
    of a project indicates that job definitions in this project which
    conflict with the named projects should be ignored, and those in
    the named project should be used instead.  The named projects must
    still appear earlier in the configuration.  In the example above,
    if a job definition appears in both the "common-config" and
    "zuul-jobs" projects, the definition in "common-config" will be
    used.

    **exclude-unprotected-branches**
    Define if unprotected github branches should be processed. Defaults to the
    tenant wide setting of exclude-unprotected-branches.

  The order of the projects listed in a tenant is important.  A job
  which is defined in one project may not be redefined in another
  project; therefore, once a job appears in one project, a project
  listed later will be unable to define a job with that name.
  Further, some aspects of project configuration (such as the merge
  mode) may only be set on the first appearance of a project
  definition.

  Zuul loads the configuration from all *config-projects* in the order
  listed, followed by all *trusted-projects* in order.
