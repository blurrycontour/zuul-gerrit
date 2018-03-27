Zuul From Scratch
=================

.. note:: This is a work in progress that attempts to walk through all
          of the steps needed to run Zuul on a all-in-one server, and
          demonstrate running against a GitHub project. The steps here
          are not intended for a production setup.

Environment Setup
-----------------

Follow the instructions below, depending on your server type.

  * :doc:`fedora27_setup`

Zuul and Nodepool Installation
------------------------------

Install Nodepool
~~~~~~~~~~~~~~~~

::

   sudo adduser --system nodepool --home-dir /var/lib/nodepool --create-home
   git clone https://git.openstack.org/openstack-infra/nodepool
   cd nodepool/
   sudo dnf -y install $(bindep -b)
   sudo pip3 install .

Install Zuul
~~~~~~~~~~~~

::

   sudo adduser --system zuul --home-dir /var/lib/zuul --create-home
   git clone https://git.openstack.org/openstack-infra/zuul
   cd zuul/
   sudo dnf install $(bindep -b) -y
   sudo pip3 install git+https://github.com/sigmavirus24/github3.py.git@develop#egg=Github3.py
   sudo pip3 install .

Setup
-----

Zookeeper Setup
~~~~~~~~~~~~~~~

.. TODO recommended reading for zk clustering setup

::

   sudo bash -c 'echo "1" > /etc/zookeeper/myid'
   sudo bash -c 'echo "tickTime=2000
   dataDir=/var/lib/zookeeper
   clientPort=2181" > /etc/zookeeper/zoo.cfg'

Nodepool Setup
~~~~~~~~~~~~~~

Before starting on this, you need to download your `openrc`
configuration from your OpenStack cloud.  Put it on your server in the
fedora user's home directory.  It should be called
``<username>-openrc.sh``.  Once that is done, create a new keypair
that will be installed when instantiating the servers::

   cd ~
   source <username>-openrc.sh  # this will prompt for password - enter it
   umask 0066

   ssh-keygen -t rsa -b 2048 -f nodepool_rsa  # don't enter a passphrase
   openstack keypair create --public-key nodepool_rsa.pub nodepool

We'll use the private key later wheen configuring Zuul.  In the same
session, configure nodepool to talk to your cloud::

   sudo mkdir -p ~nodepool/.config/openstack
   cat > clouds.yaml <<EOF
   clouds:
     mycloud:
       auth:
         username: $OS_USERNAME
         password: $OS_PASSWORD
         project_name: ${OS_PROJECT_NAME:-$OS_TENANT_NAME}
         auth_url: $OS_AUTH_URL
       region_name: $OS_REGION_NAME
   EOF
   sudo mv clouds.yaml ~nodepool/.config/openstack/
   sudo chown -R nodepool.nodepool ~nodepool/.config
   umask 0002

Once you've written out the file, double check all the required fields have been filled out.

::

   sudo mkdir /etc/nodepool/
   sudo mkdir /var/log/nodepool
   sudo chgrp -R nodepool /var/log/nodepool/
   sudo chmod 775 /var/log/nodepool/

Nodepool Configuration
~~~~~~~~~~~~~~~~~~~~~~

Inputs needed for this file:

* cloud name / region name - from clouds.yaml
* flavor-name
* image-name - from your cloud

::

   sudo bash -c "cat >/etc/nodepool/nodepool.yaml <<EOF
   zookeeper-servers:
     - host: localhost
       port: 2181

   providers:
     - name: myprovider # this is a nodepool identifier for this cloud provider (cloud+region combo)
       region-name: regionOne  # this needs to match the region name in clouds.yaml but is only needed if there is more than one region
       cloud: mycloud  # This needs to match the name in clouds.yaml
       cloud-images:
         - name: centos-7   # Defines a cloud-image for nodepool
           image-name: CentOS-7-x86_64-GenericCloud-1706  # name of image from cloud
           username: centos  # The user Zuul should log in as
       pools:
         - name: main
           max-servers: 4  # nodepool will never create more than this many servers
           labels:
             - name: centos-7-small  # defines label that will be used to get one of these in a job
               flavor-name: 'm1.small'  # name of flavor from cloud
               cloud-image: centos-7  # matches name from cloud-images
               key-name: nodepool # name of the keypair to use for authentication

   labels:
     - name: centos-7-small # defines label that will be used in jobs
       min-ready: 2  # nodepool will always keep this many booted and ready to go
   EOF"

.. warning::

   `min-ready:2` may incur costs in your cloud provider


Zuul Setup
~~~~~~~~~~

::

   sudo mkdir /etc/zuul/
   sudo mkdir /var/log/zuul/
   sudo chown zuul.zuul /var/log/zuul/
   sudo mkdir /var/lib/zuul/.ssh
   sudo chmod 0700 /var/lib/zuul/.ssh
   sudo mv nodepool_rsa /var/lib/zuul/.ssh
   sudo chown -R zuul.zuul /var/lib/zuul/.ssh

Zuul Configuration
~~~~~~~~~~~~~~~~~~

Write the Zuul config file.  Note that this configures Zuul's web
server to listen on all public addresses.  This is so that Zuul may
receive webhook events from GitHub.  You may wish to proxy this or
further restrict public access.

::

   sudo bash -c "cat > /etc/zuul/zuul.conf <<EOF
   [gearman]
   server=127.0.0.1

   [gearman_server]
   start=true

   [executor]
   private_key_file=/home/zuul/.ssh/nodepool_rsa

   [web]
   listen_address=0.0.0.0

   [scheduler]
   tenant_config=/etc/zuul/main.yaml
   EOF"

   sudo bash -c "cat > /etc/zuul/main.yaml <<EOF
   - tenant:
       name: quickstart
   EOF"

Use Zuul Jobs
-------------

Add to ``/etc/zuul/zuul.conf``::

   sudo bash -c "cat >> /etc/zuul/zuul.conf <<EOF

   [connection zuul-git]
   driver=git
   baseurl=https://git.openstack.org/
   EOF"

Restart executor and scheduler::

   sudo systemctl restart zuul-executor.service
   sudo systemctl restart zuul-scheduler.service

Setup Your Repo
---------------

Select your code repository to setup.

  * :doc:`github_setup`
