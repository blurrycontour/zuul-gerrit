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
