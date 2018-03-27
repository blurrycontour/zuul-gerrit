:orphan:

Install Zuul
============

::

   sudo adduser --system zuul --home-dir /var/lib/zuul --create-home
   git clone https://git.zuul-ci.org/zuul
   cd zuul/
   sudo dnf install $(bindep -b) -y
   sudo pip3 install .
