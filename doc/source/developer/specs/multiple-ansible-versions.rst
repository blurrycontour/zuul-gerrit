Multiple Ansible versions
=========================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

Currently zuul only supports one specific ansible version at once. This
complicates upgrading ansible because ansible often breaks backwards
compatibility and so we need to synchronize the upgrade on the complete
deployment which is often not possible.

Instead we want to support multiple ansible versions at once so we can handle
the lifecycle of ansible versions by adding new versions and deprecating old
ones.


Requirements
------------

We want jobs to be able to pick a specific ansible version to run. However as we
have lots of stuff that overrides things in ansible we will let the job only
select a minor version (e.g. 2.6) in a list of supported versions. This is also
necessary from a security point of view so the user cannot pick a specific
bugfix version that is known to contain certain security flaws. Zuul needs to
support a list of specific minor versions from where it will pick the latest
bugfix version or a pinned version if we need to.

Depending on the deployment zuul needs to be able to install ansible versions
on-demand or take pre-installed versions of ansible. E.g. in case of a
containerized installation of zuul we might want to pre-install all supported
ansible versions inside the container while in a traditional deployment we may
want to install/upgrade them during executor startup if needed.


Job configuration
-----------------

There will be a new job attribute ``ansible-version`` that will instruct zuul
to take the specified version. This attribute will be validated against a list
of supported ansible versions that zuul currently can handle. Zuul will throw
a configuration error if a job selects an unsupported or unparsable version.
If no ``ansible-version`` is defined zuul will pick up the ansible version
marked as default. We will also need a mechanism to deprecate ansible versions
to prepare removing old versions. We could add labels to the supported versions.
To express that. The supported versions we will start with will be:

* 2.5 (deprecated, default)
* 2.6
* 2.7

In a second phase we will switch the default ansible version to the highest
release available at that time. This step needs proper announcement on the
mailing list which is the reason to split supporting multiple versions and
switching the default. The then supported list could be:

* 2.5 (deprecated)
* 2.6
* 2.7 (default)

We will also need to be able to pin a version to a specific bugfix version in
case the latest one is known to be broken. This will also be handled by the
installation mechanisms describes below.


Installing ansible
------------------

We currently pull in ansible via the ``requirements.txt``. This will no longer
be sufficient. Instead zuul itself needs to take care of installing the
supported versions into a pre-defined directory structure using virtualenv. The
executor will have two new config options:

* ``ansible-root``: The root path where ansible installations will be found. The
  default will be ``/var/lib/executor-ansible``. All supported ansible
  installations will live inside a virtualenv in the path
  ``ansible-root/<minor-version>``.

* ``manage-ansible``: A boolean flag that tells the executor manage the
  installed ansible versions itself. The default will be ``true``.

  If set to ``true`` the executor will install and upgrade all supported
  ansible versions on startup.

  If set to ``false`` the executor will validate the presence of all supported
  ansible versions on startup.

We also need a script in ``tools`` that installs every supported version of
ansible into a specified ``ansible-root``. This will be needed for the tests
as well as for easily supporting the pre-installed ansible-versions use case.


Ansible module overrides
------------------------

We currently have many ansible module overrides. These may or may not be
targeted to a specific ansible version. Currently they are organized into the
folder ``zuul/ansible``. In order to support multiple ansible versions without
needing to fork everything there this will be reorganized into:

* ``zuul/ansible/generic``: Overrides and modules valid for all supported
   ansible versions.
* ``zuul/ansible/<version>``: Overrides and modules valid for a specific
  version.

If there are overrides that are valid for a range of ansible versions we can
define it in the lowest version and make use of symlinking to the other versions
in order to minimize additional maintenance overhead by not forking an override
where possible. Generally we should strive for having as much as possible in the
generic part to minimize the maintenance effort of these.


Deprecation policy
------------------

We should handle deprecating and removing supported ansible versions similar to
the deprecation policy described in zuul-jobs:
https://zuul-ci.org/docs/zuul-jobs/policy.html

We also should notify the users when they use deprecated ansible versions. This
can be done in two ways. First the executor will emit a warning to the logs when
it encounters a job that uses a deprecated ansible version. Second we can add a
new variable ``zuul.warnings`` to the job that includes a list of warnings that
can be added to the job variables. A base job can print a banner with all
warnings at the start of the job to also inform the users about e.g. using
deprecated ansible versions or also other deprecated things which might arise in
the future.


Testing
-------

We also have a set of tests that validate the security overrides. We need to
test them for all supported ansible versions. Where needed we also need to fork
or add additional version specific tests.
