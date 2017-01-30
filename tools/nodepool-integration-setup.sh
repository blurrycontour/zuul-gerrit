#!/bin/bash -xe

# Install bindep.txt for zuul
/usr/local/jenkins/slave_scripts/install-distro-packages.sh

/usr/zuul-env/bin/zuul-cloner --workspace /tmp --cache-dir /opt/git \
    git://git.openstack.org openstack-infra/nodepool

ln -s /tmp/nodepool/log $WORKSPACE/logs

cd /tmp/openstack-infra/nodepool
/usr/local/jenkins/slave_scripts/install-distro-packages.sh
sudo pip install .

# Launch fedmsg-tail in screen
sudo pip install fedmsg[commands]
screen -dm -S fedmsg-tail "fedmsg-tail | tee $WORKSPACE/logs/fedmsg-tail.log"

bash -xe ./tools/zuul-nodepool-integration/start.sh
