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


List playbooks
--------------

The --list-playbooks toggle clones all the required repositories and
prepare the Ansible playbook so that a developer can run the
steps individually (and interact where they need).

For example, to prepare the tempest job workspace of the Nova project:

.. code-block:: shell

   $ zuul-runner --api https://zuul.openstack.org --project openstack/nova \
       --job tempest-full-py3 --list-playbooks
   == Pre phase ==
   0: opendev.org/opendev/base-jobs/playbooks/base/pre.yaml
   1: opendev.org/zuul/zuul-jobs/playbooks/multinode/pre.yaml
   2: opendev.org/openstack/devstack/playbooks/pre.yaml
   == Run phase ==
   3: opendev.org/openstack/tempest/playbooks/devstack-tempest.yaml
   == Post phase ==
   4: opendev.org/openstack/tempest/playbooks/post-tempest.yaml
   5: opendev.org/openstack/devstack/playbooks/post.yaml
   6: opendev.org/opendev/base-jobs/playbooks/base/post.yaml
   7: opendev.org/opendev/base-jobs/playbooks/base/post-logs.yaml
