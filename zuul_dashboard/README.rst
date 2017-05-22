A jenkins-like dashboard for Zuul
=================================

Installation
------------

pushd etc/status/ && ./fetch-dependencies.sh && popd
rsync -a etc/status/public_html/ /var/www/public_html/
cat<<EOF> /etc/httpd/conf.d/zuul_dashboard.conf
ProxyPass /zuul_dashboard/ http://localhost:8080/zuul_dashboard/ nocanon retry=0
ProxyPassReverse /zuul_dashboard/ http://localhost:8080/zuul_dashboard/
EOF
systemctl reload httpd

Configuration
-------------

# Change dburi in config.py
$EDITOR zuul_dashboard/config.py

Execution
---------

PYTHONPATH=$(pwd) pecan serve zuul_dashboard/config.py

Then open http://localhost/public_html/dashboard.html
