Zuul From Scratch
=================

Environment Setup
-----------------

We're going to be using Fedora 27 on a cloud server for this
installation.

Login to your environment
~~~~~~~~~~~~~~~~~~~~~~~~~

Since we'll be using a cloud image for Fedora 27, our login user will
be ``fedora`` which will also be the staging user for installation of
Zuul and Nodepool.

To get started, ssh to your machine as the ``fedora`` user::

   ssh fedora@<ip_address>

Environment Setup
~~~~~~~~~~~~~~~~~

::

   sudo dnf update -y
   sudo systemctl reboot
   sudo dnf install git redhat-lsb-core -y

Python Dependencies
~~~~~~~~~~~~~~~~~~~

::

   sudo yum install python3 python3-pip python3-devel make gcc openssl-devel -y
   pip3 install --user bindep


Zuul and Nodepool Installation
------------------------------

Install Zookeeper
~~~~~~~~~~~~~~~~~

::

   sudo dnf install zookeeper -y

Install Nodepool
~~~~~~~~~~~~~~~~

::

   sudo adduser nodepool
   git clone https://git.openstack.org/openstack-infra/nodepool
   cd nodepool/
   sudo dnf -y install $(bindep -b)
   sudo pip3 install .

Install Zuul
~~~~~~~~~~~~

::

   sudo adduser zuul
   git clone https://git.openstack.org/openstack-infra/zuul
   cd zuul/
   sudo dnf install $(bindep -b) -y
   sudo pip3 install git+https://github.com/sigmavirus24/github3.py.git@develop#egg=Github3.py
   sudo pip3 install .

Setup
-----

Zookeeper Setup
~~~~~~~~~~~~~~~

::

   sudo bash -c 'echo "1" > /etc/zookeeper/myid'
   sudo bash -c 'echo "tickTime=2000
   dataDir=/var/lib/zookeeper
   clientPort=2181" > /etc/zookeeper/zoo.cfg'

Nodepool Setup
~~~~~~~~~~~~~~

Before starting on this, you need to download your `openrc`
configuration from your OpenStack cloud.

Create Keypair

In your OpenStack instance, create a new keypair that can be used for
instantiating the servers. You can do this in Horizon and then simply
download the key onto your Zuul instance. In our `nodepool.yaml`
configuration, we set the `key-name` value to `nodepool`. When
creating your keypair, name them the same.

Once the keypair is created, you'll need to keep the private key
safe. We'll eventually upload it to the Zuul instance, placing it in
the `/home/zuul/.ssh/nodepool.pem` location on the server.

.. TODO install shade and do this all from the console instead of
   telling someone to go to the web interface

::

   cd ~
   source <username>-openrc.sh # this will prompt for password - enter it
   sudo mkdir -p /home/nodepool/.config/openstack
   cat > /tmp/clouds.yaml <<EOF
   clouds:
     mycloud:
       auth:
         username: $OS_USERNAME
         password: $OS_PASSWORD
         project_name: $OS_PROJECT_NAME
         auth_url: $OS_AUTH_URL
       region_name: $OS_REGION_NAME
   EOF
   sudo mv /tmp/clouds.yaml /home/nodepool/.config/openstack/
   sudo chown -R nodepool.nodepool /home/nodepool/.config


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
       pools:
         - name: main
           max-servers: 4  # quota - nodepool will never create more than this many
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
   sudo mkdir /var/lib/zuul/
   sudo chown -R zuul.zuul /var/lib/zuul
   sudo mkdir /var/log/zuul/
   sudo chown zuul.zuul /var/log/zuul/
   sudo mkdir /home/zuul/.ssh
   sudo chown zuul.zuul /home/zuul/.ssh
   sudo chmod 0700 /home/zuul/.ssh

Upload the nodepool key from earlier to
``/var/lib/zuul/.ssh/nodepool.pem``.

Zuul Configuration
~~~~~~~~~~~~~~~~~~

::

   sudo bash -c "cat > /etc/zuul/zuul.conf <<EOF
   [gearman]
   server=127.0.0.1

   [gearman_server]
   start=true

   [executor]
   private_key_file=/home/zuul/.ssh/nodepool.pem
   default_username=centos
   finger_port=17979

   [scheduler]
   tenant_config=/etc/zuul/main.yaml
   EOF"

   sudo bash -c "cat > /etc/zuul/main.yaml <<EOF
   - tenant:
       name: quickstart
   EOF"

Service Management
------------------

Zookeeper Service Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   sudo systemctl start zookeeper.service

::

   sudo systemctl status zookeeper.service
   ● zookeeper.service - Apache ZooKeeper
      Loaded: loaded (/usr/lib/systemd/system/zookeeper.service; disabled; vendor preset: disabled)
      Active: active (running) since Wed 2018-01-03 14:53:47 UTC; 5s ago
     Process: 4153 ExecStart=/usr/bin/zkServer.sh start zoo.cfg (code=exited, status=0/SUCCESS)
    Main PID: 4160 (java)
       Tasks: 17 (limit: 4915)
      CGroup: /system.slice/zookeeper.service
              └─4160 java -Dzookeeper.log.dir=/var/log/zookeeper -Dzookeeper.root.logger=INFO,CONSOLE -cp /usr/share/java/

::

   sudo systemctl enable zookeeper.service


Nodepool Service Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   sudo bash -c "cat > /etc/systemd/system/nodepool-launcher.service <<EOF
   [Unit]
   Description=Nodepool Launcher Service
   After=syslog.target network.target

   [Service]
   Type=simple
   # Options to pass to nodepool-launcher.
   Group=nodepool
   User=nodepool
   RuntimeDirectory=nodepool
   ExecStart=/usr/bin/nodepool-launcher

   [Install]
   WantedBy=multi-user.target
   EOF"

   sudo chmod 0644 /etc/systemd/system/nodepool-launcher.service
   sudo systemctl daemon-reload
   sudo systemctl start nodepool-launcher.service
   sudo systemctl status nodepool-launcher.service
   sudo systemctl enable nodepool-launcher.service

Zuul Service Management
~~~~~~~~~~~~~~~~~~~~~~~
::

   sudo bash -c "cat > /etc/systemd/system/zuul-scheduler.service <<EOF
   [Unit]
   Description=Zuul Scheduler Service
   After=syslog.target network.target

   [Service]
   Type=simple
   Group=zuul
   User=zuul
   RuntimeDirectory=zuul
   ExecStart=/usr/local/bin/zuul-scheduler
   ExecStop=/usr/local/bin/zuul-scheduler stop

   [Install]
   WantedBy=multi-user.target
   EOF"
   sudo bash -c "cat > /etc/systemd/system/zuul-executor.service <<EOF
   [Unit]
   Description=Zuul Executor Service
   After=syslog.target network.target

   [Service]
   Type=simple
   Group=zuul
   User=zuul
   RuntimeDirectory=zuul
   ExecStart=/usr/local/bin/zuul-executor
   ExecStop=/usr/local/bin/zuul-executor stop

   [Install]
   WantedBy=multi-user.target
   EOF"

   sudo systemctl daemon-reload
   sudo systemctl start zuul-scheduler.service
   sudo systemctl status zuul-scheduler.service
   sudo systemctl enable zuul-scheduler.service
   sudo systemctl start zuul-executor.service
   sudo systemctl status zuul-executor.service
   sudo systemctl enable zuul-executor.service

WIP HERE

# Setup NoOp Job
**TODO** here is where we'll setup a base configuration using the gtest-org setup to pull in an example Zuul project
configuration, that allows us to instantiate a job from the console. We'll also use the `keep` configuration so that
we don't need to setup a full logging server at this time.

# Firewall Setup

    sudo firewall-cmd --permanent --add-port=80/tcp
    sudo firewall-cmd --permanent --add-port=9000/tcp
    sudo firewall-cmd --permanent --add-port=8001/tcp
    sudo firewall-cmd --reload


# Other

## Github stuff

setup an app: https://developer.github.com/apps/building-integrations/setting-up-and-registering-github-apps/registering-github-apps/

homepage url: doesn't matter

user auth callback url http://IPADDR:8001/

http://IPADDR:8001/connection/github/payload

https://screenshots.firefox.com/FkHTNZFbA784ukSa/github.com
https://screenshots.firefox.com/isar1xCFXNmlc0uR/github.com

    [zuul@nfvpe-zuulv3 ~]$ ssh-keygen  

    sudo bash -c "cat >> /etc/zuul/zuul.conf <<EOF
    [connection github]
    driver=github
    app_id=<app_id>
    app_key=/etc/zuul/github.key
    webhook_token=<webhook_token>
    EOF"

## Phase 1: Zuul Pipeline Configuration


2 kinds of repos:
- config projects
    - ones that are treated special, expected to be dedicated to zuul configuration
    - allowed to do things that would otherwise be insecure in other contexts
- untrusted projects
    - anything else; real dev project; zuul jobs repo (for example)
    
* zuul-qs-config/zuul.d/pipeline.yaml

## Changes to main.yaml

    - tenant:
        name: quickstart
        exclude-unprotected-branches: true
        source:
          github:
            config-projects:
              - leifmadsen/zuul-qs-config
            untrusted-projects:
              - leifmadsen/dummy-commits
