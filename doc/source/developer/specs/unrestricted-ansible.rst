Unrestricted Ansible
====================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.


Overview
--------

Zuul currently uses a restricted version of Ansible to run playbooks
in the `untrusted` execution context.  This is accomplished by
inserting custom Ansible plugins into the plugin load paths so that
they are found by Ansible before the standard plugins.  Generally the
custom plugins do one of two things: prevent execution entirely, or
verify that file paths are within the work dir before allowing normal
execution.

Each new version of Ansible requires an examination of any new plugins
to see if they must be restricted as well as auditing of existing
plugins to see if their interface or behavior has changed in such a
way that the custom plugins must be updated.

In addition, the executor examines the contents of repos it checks out
to verify that Ansible will not attempt to load any plugins which are
adjacent to playbooks.

Currently, Zuul supports Ansible 2.9 as the latest version.  It is no
longer maintained.

More recent Ansible versions have significantly altered the internal
plugin loading framework to accommodate Ansible Collections.  This
brings new challenges:

#. The number of plugins included in the community edition of Ansible
   (the "batteries-included") is considerably larger than that in
   Ansible 2.9 (meanwhile, the set in Ansible core is smaller than
   that in 2.9).

#. The process of loading plugins differs depending on how they are
   named (e.g., using the `csvfile` lookup plugin causes different
   plugin loading machinery than its alias `ansible.builtin.csvfile`).
   We would need to find a way to hook into the new system as well as
   using the system we currently employ.

In total, this greatly increases the complexity of what Zuul needs to
do to override plugins while increasing the surface area that Zuul
developers need to monitor.

It is very likely that we can obtain a facsimile of the current
behavior with newer versions of Ansible, but it will require far more
work.

At the same time, the restricted Ansible environment has proven to be
a hindrance to using Zuul in many use cases, notably for lightweight
jobs which don't need a remote node, or continuous deployment where a
nested Ansible must be run in order to use certain features of
Ansible.

The reason we have the restricted environment in the first place is
due to security considerations.  See below for more details.


Proposed Change
---------------

Remove the restricted Ansible execution environment so that all
playbooks run with the full feature set of Ansible available.  Note
that trusted and untrusted execution environments will remain since
they also have meaning within Zuul related to secrets as well as
conditional mountpoints within the build directory.

Once this is done, we can easily support new versions of Ansible.

Implementation
--------------

The implementation will entail:

* Removing the custom plugins which override built-in Ansible plugins.

* Removing the checks for plugins adjacent to playbooks.

* Updating or removing tests which verify the custom plugin behavior.

* Adding support for Ansible 5.4.

* Documenting the security considerations described below.

This has significant impact to operators and so will be communicated
with a Zuul major version increase.

Security Considerations
-----------------------

Removing the restricted environment certainly weakens Zuul's security
posture, however the degree to which it does so may be sufficiently
small to warrant the risk.  The following are the main areas of
concern:

Access to Local Resources
~~~~~~~~~~~~~~~~~~~~~~~~~

Local plugin or code execution may allow access to executor resources.

Untrusted playbooks should not be allowed to read arbitrary files on
the executor, or execute programs which run in the background and
steal secrets from later playbooks.

This is mitigated by the use of bubblewrap which only allows access to
files explicitly added to the bubblewrap environment (and controlled
by the Zuul operator).  It also ensures that the process group is
terminated at the end of each playbook run.

Zuul operators will need to be aware that untrusted playbooks will
have access to more files which are made available to the bubblewrap
environment than before.  See `WinRM Credentials` below for one
specific case.

Local Code Execution
~~~~~~~~~~~~~~~~~~~~

The ability to execute arbitrary code locally combined with a
potential future local root exploit could allow an attacker to gain
control of the Zuul system.

Operators will need to be cognizant of the risk and keep systems up to
date and pro-actively rebuild executor servers and rotate credentials
in the case of possible compromise.

Local Network Access
~~~~~~~~~~~~~~~~~~~~

If the Zuul executor is run in a network environment which is trusted,
then users may be able to take advantage of that to access restricted
systems.

Zuul operators should ensure that executors do not have
unauthenticated access to any trusted systems.

Within Zuul itself, connections to ZooKeeper are authenticated and
encrypted, so should not be a concern.

It is worth noting that statsd operates over UDP without
authentication, so users could emit falsified stats information from
the executor.  The risk of mischief may be seen as small in most
environments.  If it is nonetheless unacceptable, operators may
disable statsd in the executors and restrict access.

In the future, this risk can be further mitigated by moving executor
stats to Prometheus (which is a pull rather than push based system).

Cloud Metadata
~~~~~~~~~~~~~~

A special case of local network access is the ability to access
metadata servers if the executor is running in a cloud environment.

Because a Zuul job would be able to open a connection to the metadata
server and retrieve information, operators will need to ensure that no
sensitive data are provided to the executors via the metadata service,
and that it is not provided with any IAM profiles which should not be
available to jobs.

WinRM Credentials
~~~~~~~~~~~~~~~~~

The executor keeps SSH keys outside of the bubblewrap environment and
uses an SSH agent to provide them to Ansible.  The same is not true
for WinRM credentials which are supplied as files that must be mounted
within the environment.  Operators may be relying on the file access
controls in custom plugins to avoid leaking the WinRM credentials to
end-users.

To remedy this, operators may switch to supplying the WinRM
credentials only to trusted playbooks, and then running a pre-run
playbook in a base job to create temporary WinRM credentials (similar
to the build ssh keys that zuul-jobs uses) for use by later playbooks.
The playbook would set the hostvars for the affected hosts to use the
new paths of the temporary certificates.

(A further improvement to this would be to add a new feature to Zuul
to provide the initial WinRM certificate as a secret so that only the
base job playbook would have access to it, not any other trusted
playbooks.  This is not strictly necessary for parity with the current
system though, and is out of scope of this spec.)

Summary
~~~~~~~

Because of the "best-effort" nature of Zuul's custom plugins, many of
the preceding avenues of attack may already be present today.  Several
previous vulnerabilities in Zuul have related to the ability to bypass
these measures and we have relied entirely on bubblewrap to contain
the fallout.  Removing the restricted environment does remove a layer
from our defense in depth, but that layer may not be very effective in
the first place.
