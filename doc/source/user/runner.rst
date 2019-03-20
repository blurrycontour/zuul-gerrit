:title: Runner

.. _runner:

Zuul Runner
===========

Zuul includes a command line interface to execute job locally.

Usage
-----

.. program-output:: zuul-runner --help


Example
-------

To execute the tempest job of nova:

.. code-block:: shell

   pip install --user zuul
   zuul-runner --api https://zuul.openstack.org --project openstack/nova \
     --job tempest-full --node ssh:ubuntu-bionic:instance-ip:ubuntu:/home/ubuntu

Your local user must be able to connect to the git source with ssh.


Configuration
-------------

A configuration file may be provided to define the nodes and to
set custom secrets:

.. code-block:: yaml

   # ~/.config/zuul/runner.yaml
   connections:
     - name: gerrit
       user: tristanC
       keyfile: /home/centos/.ssh/opendev_gerrit_rsa
   nodes:
     - label: centos-7
       username: centos
       hostname: test-instance.cloud.rdoproject.org
   secrets:
     site_logs_project_config:
       fqdn: localhost
       ssh_username: www-logs
       path: /var/www/htdocs/zuul-runner-logs


.. note::

   In the futur:

   * Connections username may become optional if the Source driver support
     anonymous http access.
   * Nodes may be replaced by a nodepool configuration to be used for
     handling test instance lifecycle using nodepool drivers.
