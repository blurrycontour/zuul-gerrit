:orphan:

Install Zuul
============

Initial setup steps are common across different Linux distributions but Zuul
installation steps differ between the distributions.

Please follow the steps listed in initial setup and then move to the chapter
for the Linux distribution you have chosen to install Zuul on.

Initial Setup
=============

.. code-block:: console

   $ sudo adduser --system zuul --home-dir /var/lib/zuul --create-home
   $ sudo mkdir /etc/zuul/
   $ sudo mkdir /var/log/zuul/
   $ sudo chown zuul.zuul /var/log/zuul/
   $ sudo mkdir /var/lib/zuul/.ssh
   $ sudo chmod 0700 /var/lib/zuul/.ssh
   $ sudo mv nodepool_rsa /var/lib/zuul/.ssh
   $ sudo chown -R zuul.zuul /var/lib/zuul/.ssh

Install Zuul on Fedora 27
=========================

.. code-block:: console

   $ git clone https://git.zuul-ci.org/zuul
   $ cd zuul/
   $ sudo dnf install $(bindep -b) -y
   $ sudo pip3 install .

Service Files
-------------

Zuul includes some systemd service files for Zuul in the ``etc`` source
directory. To use them, do the following steps.

.. code-block:: console

  $ sudo cp etc/zuul-scheduler.service /etc/systemd/system/zuul-scheduler.service
  $ sudo cp etc/zuul-executor.service /etc/systemd/system/zuul-executor.service
  $ sudo cp etc/zuul-web.service /etc/systemd/system/zuul-web.service
  $ sudo chmod 0644 /etc/systemd/system/zuul-scheduler.service
  $ sudo chmod 0644 /etc/systemd/system/zuul-executor.service
  $ sudo chmod 0644 /etc/systemd/system/zuul-web.service

Install Zuul on CentOS 7
========================

.. code-block:: console

   $ git clone https://git.zuul-ci.org/zuul
   $ cd zuul/
   $ sudo yum install -y $(bindep -b)
   $ sudo pip3 install .

Service Files
-------------

Zuul includes some systemd service files for Zuul in the ``etc`` source
directory. For CentOS 7, the drop-in files are also needed to be able to use
provided systemd service files since pip installs Zuul components into different
location on CentOS 7. With the provided drop-in files, systemd overrides
``ExecStart`` and ``ExecStop`` entries properly and the services can be started.

.. code-block:: console

  $ sudo cp etc/zuul-scheduler.service /etc/systemd/system/zuul-scheduler.service
  $ sudo mkdir /etc/systemd/system/zuul-scheduler.service.d
  $ sudo cp etc/zuul-scheduler.service.d/centos.conf \
      /etc/systemd/system/zuul-scheduler.service.d/centos.conf
  $ sudo cp etc/zuul-executor.service /etc/systemd/system/zuul-executor.service
  $ sudo mkdir /etc/systemd/system/zuul-executor.service.d
  $ sudo cp etc/zuul-executor.service.d/centos.conf \
      /etc/systemd/system/zuul-executor.service.d/centos.conf
  $ sudo cp etc/zuul-web.service /etc/systemd/system/zuul-web.service
  $ sudo mkdir /etc/systemd/system/zuul-web.service.d
  $ sudo cp etc/zuul-web.service.d/centos.conf \
      /etc/systemd/system/zuul-web.service.d/centos.conf
  $ sudo chmod 0644 /etc/systemd/system/zuul-scheduler.service \
      /etc/systemd/system/zuul-scheduler.service.d/centos.conf
  $ sudo chmod 0644 /etc/systemd/system/zuul-executor.service \
      /etc/systemd/system/zuul-executor.service.d/centos.conf
  $ sudo chmod 0644 /etc/systemd/system/zuul-web.service \
      /etc/systemd/system/zuul-web.service.d/centos.conf
