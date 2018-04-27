:orphan:

Initial Setup
=============

.. code-block:: console

   $ sudo adduser --system nodepool --home-dir /var/lib/nodepool --create-home
   $ ssh-keygen -t rsa -b 2048 -f nodepool_rsa  # don't enter a passphrase
   $ sudo mkdir /etc/nodepool/
   $ sudo mkdir /var/log/nodepool
   $ sudo chgrp -R nodepool /var/log/nodepool/
   $ sudo chmod 775 /var/log/nodepool/

Install Nodepool on Fedora 27
=============================

::

   git clone https://git.zuul-ci.org/nodepool
   cd nodepool/
   sudo dnf -y install $(bindep -b)
   sudo pip3 install .

Service File
------------

Nodepool includes a systemd service file for nodepool-launcher in the ``etc``
source directory. To use it, do the following steps::

  $ sudo cp etc/nodepool-launcher.service /etc/systemd/system/nodepool-launcher.service
  $ sudo chmod 0644 /etc/systemd/system/nodepool-launcher.service

Install Nodepool on CentOS 7
============================

.. code-block:: console

   $ git clone https://git.zuul-ci.org/nodepool
   $ cd nodepool/
   $ sudo yum install -y $(bindep -b)
   $ sudo pip3 install .

Service File
------------

Nodepool includes a systemd service file for nodepool-launcher in the ``etc``
source directory. For CentOS 7, the drop-in file is also needed to be able to use
provided systemd service file since pip installs Nodepool into different location
on CentOS 7. With the provided drop-in file, systemd overrides ``ExecStart`` entry
properly and the service can be started.

.. code-block:: console

   $ sudo cp etc/nodepool-launcher.service /etc/systemd/system/nodepool-launcher.service
   $ sudo mkdir /etc/systemd/system/nodepool-launcher.service.d
   $ sudo cp etc/nodepool-launcher.service.d/centos.conf \
        /etc/systemd/system/nodepool-launcher.service.d/centos.conf
   $ sudo chmod 0644 /etc/systemd/system/nodepool-launcher.service \
        /etc/systemd/system/nodepool-launcher.service.d/centos.conf
