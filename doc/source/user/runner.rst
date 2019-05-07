:title: Runner

.. _runner:

Zuul Runner
===========

Zuul includes a command line interface to execute job locally.

Usage
-----

.. program-output:: zuul-runner --help

Zuul-runner uses the local user name and ssh key from ~/.ssh/id_rsa.
Make sure ssh access to resources is enabled.


Prepare Workspace
-----------------

.. program-output:: zuul-runner prepare-workspace --help

The prepare-workspace sub command clone all the required repositories and
prepare the Ansible playbook so that a developer can run the
steps individually (and interact where they need).

For example, to prepare the tempest job workspace of the Nova project:

.. code-block:: shell

   $ pip install --user zuul
   $ zuul-runner --api https://zuul.openstack.org --project openstack/nova \
       --job tempest-full-py3 prepare-workspace
   == Pre phase ==
   /tmp/tmp4b58gpfz/trusted/project_0/opendev.org/opendev/base-jobs/playbooks/base/pre.yaml
   /tmp/tmp4b58gpfz/untrusted/project_1/opendev.org/zuul/zuul-jobs/playbooks/multinode/pre.yaml
   /tmp/tmp4b58gpfz/untrusted/project_2/opendev.org/openstack/devstack/playbooks/pre.yaml
   == Run phase ==
   /tmp/tmp4b58gpfz/untrusted/project_3/opendev.org/openstack/tempest/playbooks/devstack-tempest.yaml
   == Post phase ==
   /tmp/tmp4b58gpfz/untrusted/project_3/opendev.org/openstack/tempest/playbooks/post-tempest.yaml
   /tmp/tmp4b58gpfz/untrusted/project_2/opendev.org/openstack/devstack/playbooks/post.yaml
   /tmp/tmp4b58gpfz/trusted/project_0/opendev.org/opendev/base-jobs/playbooks/base/post.yaml
   /tmp/tmp4b58gpfz/trusted/project_0/opendev.org/opendev/base-jobs/playbooks/base/post-logs.yaml


Execute
-------

.. program-output:: zuul-runner execute --help

For example, to execute the tempest job of the Nova project:

.. code-block:: shell

   $ zuul-runner --api https://zuul.openstack.org --project openstack/nova \
       --job tempest-full-py3 execute --nodes ssh:ubuntu-bionic:instance-ip:tdecacqu:/home/tdecacqu
   [...]
   2019-05-07 06:08:01,040 DEBUG zuul.Runner - Ansible output: b'PLAY RECAP *********************************************************************'
   2019-05-07 06:08:01,040 DEBUG zuul.Runner - Ansible output: b'instance-ip                : ok=9    changed=5    unreachable=0    failed=0'
   2019-05-07 06:08:01,040 DEBUG zuul.Runner - Ansible output: b'localhost                  : ok=12   changed=9    unreachable=0    failed=0'
   2019-05-07 06:08:01,040 DEBUG zuul.Runner - Ansible output: b''
   2019-05-07 06:08:01,218 DEBUG zuul.Runner - Ansible output terminated
   2019-05-07 06:08:01,219 DEBUG zuul.Runner - Ansible cpu times: user=0.00, system=0.00, children_user=0.00, children_system=0.00
   2019-05-07 06:08:01,219 DEBUG zuul.Runner - Ansible exit code: 0
   2019-05-07 06:08:01,219 DEBUG zuul.Runner - Stopped disk job killer
   2019-05-07 06:08:01,220 DEBUG zuul.Runner - Ansible complete, result RESULT_NORMAL code 0
   2019-05-07 06:08:01,220 DEBUG zuul.ExecutorServer - Sent SIGTERM to SSH Agent, {'SSH_AUTH_SOCK': '/tmp/ssh-SYKgxg36XMBa/agent.18274', 'SSH_AGENT_PID': '18275'}
   SUCCESS
