#!/bin/bash -xe

/usr/zuul-env/bin/zuul-cloner --cache-dir /opt/git git://git.openstack.org \
    /opt/nodepool openstack-infra/nodepool

cd /opt/nodepool
/usr/local/jenkins/slave_scripts/install-distro-packages.sh
sudo pip install .

bash -xe /opt/nodepool/tools/zuul-nodepool-integration/start.sh
