#!/bin/bash -xe

/usr/zuul-env/bin/zuul-cloner --cache-dir /opt/git git://git.openstack.org \
    /tmp/nodepool-git openstack-infra/nodepool

cd /tmp/nodepool-git
/usr/local/jenkins/slave_scripts/install-distro-packages.sh
sudo pip install .

bash -xe /tmp/nodepool-git/tools/zuul-nodepool-integration/start.sh
