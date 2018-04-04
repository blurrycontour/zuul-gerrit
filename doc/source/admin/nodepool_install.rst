:orphan:

Install Nodepool
================

::

   sudo adduser --system nodepool --home-dir /var/lib/nodepool --create-home
   git clone https://git.zuul-ci.org/nodepool
   cd nodepool/
   sudo dnf -y install $(bindep -b)
   sudo pip3 install .

Service File
------------

Zuul includes a sample systemd service file for nodepool in the ``etc`` source
directory. To use it, do the following steps::

  $ sudo cp etc/nodepool-launcher.service-sample /etc/systemd/system/nodepool-launcher.service
  $ sudo chmod 0644 /etc/systemd/system/nodepool-launcher.service
