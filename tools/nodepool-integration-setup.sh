#!/bin/bash -xe

/usr/zuul-env/bin/zuul-cloner --workspace /tmp --cache-dir /opt/git \
    git://git.openstack.org openstack-infra/nodepool

ln -s /tmp/nodepool/log $HOME/logs

cd /tmp/openstack-infra/nodepool
sudo pip3 install .

bash -xe ./tools/zuul-nodepool-integration/start.sh
