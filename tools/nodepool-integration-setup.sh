#!/bin/bash -xe

/usr/zuul-env/bin/zuul-cloner --workspace /tmp --cache-dir /opt/git \
    git://git.openstack.org openstack-infra/nodepool

ln -s /tmp/nodepool/log $WORKSPACE/logs

sudo pip install fedmsg[commands]
sudo cp -a $WORKSPACE/tools/fedmsg.d /etc
# Launch fedmsg-tail in screen
screen -dmS fedmsg-tail -L "fedmsg-tail"

cd /tmp/openstack-infra/nodepool
/usr/local/jenkins/slave_scripts/install-distro-packages.sh
sudo pip install .

bash -xe ./tools/zuul-nodepool-integration/start.sh

mv $WORKSPACE/screenlog.0 $WORKSPACE/logs/fedmsg-tail.log
