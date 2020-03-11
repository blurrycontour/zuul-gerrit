ZooKeeper Administration
========================

This section will cover some basic tasks and recommendations when
setting up ZooKeeper for use with Zuul.  A complete tutorial for
ZooKeeper is out of scope for this documentation.

Configuration
-------------

The following general configuration setting in
``/etc/zookeeper/zoo.cfg`` is recommended:

.. code-block::

   autopurge.purgeInterval=6

This instructs ZooKeeper to purge old snapshots every 6 hours.  This
will avoid filling the disk.

Authentication
--------------

ZooKeeper supports password authentication via SASL.  The following settings in
``/etc/zookeeper/zoo.cfg`` will enable this:

.. code-block::

   requireClientAuthScheme=sasl
   authProvider.1=org.apache.zookeeper.server.auth.SASLAuthenticationProvider

Add the following to ``/etc/default/zookeeper``:

.. code-block::

   JAVA_OPTS="-Djava.security.auth.login.config=/etc/zookeeper/auth.conf"

And create a file at ``/etc/zookeeper/auth.conf`` with contents
similar to the following:

.. code-block::

   Client {
      org.apache.zookeeper.server.auth.DigestLoginModule required
        username="super"
        password="changeme";
   };
   Server {
      org.apache.zookeeper.server.auth.DigestLoginModule required
        user_super="changeme";
   };

Adjust the password, ``changeme`` as appropriate, then configure Zuul
to connect to Zookeeper with the username and password values supplied
here.

Encrypted Connections
---------------------

ZooKeeper version 3.5.1 or greater is required for TLS support.
ZooKeeper performs hostname and certificate validation, therefore each
member of the ZooKeeper cluster should have its own certificate.  The
``tools/zk-ca.sh`` script in the Zuul source code repository can be
used to quickly and easily generate self-signed certificates for all
ZooKeeper cluster members and clients.

Make a directory for it to store the certificates and CA data, and run
it once for each client:

.. code-block::

   mkdir /etc/zookeeper/ca
   tools/zk-ca.sh /etc/zookeeper/ca zookeeper1.example.com
   tools/zk-ca.sh /etc/zookeeper/ca zookeeper2.example.com
   tools/zk-ca.sh /etc/zookeeper/ca zookeeper3.example.com

Add the following to ``/etc/zookeeper/zoo.cfg``:

.. code-block::
   # Necessary for TLS support
   serverCnxnFactory=org.apache.zookeeper.server.NettyServerCnxnFactory

   # Client TLS configuration
   secureClientPort=2281
   ssl.keyStore.location=/etc/zookeeper/ca/keystores/zookeeper1.example.com.jks
   ssl.keyStore.password=keystorepassword
   ssl.trustStore.location=/etc/zookeeper/ca/certs/cacert.pem

   # Server TLS configuration
   sslQuorum=true
   ssl.quorum.keyStore.location=/etc/zookeeper/ca/keystores/zookeeper1.example.com.jks
   ssl.quorum.keyStore.password=keystorepassword
   ssl.quorum.trustStore.location=/etc/zookeeper/ca/certs/cacert.pem

Change the name of the certificate filenames as appropriate for the
host (e.g., ``zookeeper1.example.com.jks``).  Note that the keystore
password ``keystorepassword``, which is set by the ``zk-ca.sh``
script, does not need to be changed as long as file permissions
provide sufficient protection.  The password is present because many
Java utilities misbehave when interacting with keystores with empty or
missing passwords.

In order to disable plaintext connections, ensure that the
``clientPort`` option does not appear in ``zoo.cfg``.  Use the new
method of specifying Zookeeper quorum servers, which looks like this:

.. code-block::

   server.1=zookeeper1.example.com:2888:3888
   server.2=zookeeper2.example.com:2888:3888
   server.3=zookeeper3.example.com:2888:3888

This format normally includes ``;2181`` at the end of each line,
signifying that the server should listen on port 2181 for plaintext
client connections (this is equivalent to the ``clientPort`` option).
Omit it to disable plaintext connections.  The earlier addition of
``secureClientPort`` to the config file instructs ZooKeeper to listen
for encrypted connections on port 2281.

Be sure to specify port 2281 rather than the standard 2181 in the
:attr:`zookeeper.hosts` setting in ``zuul.conf``.

Finally, add the :attr:`zookeeper.tls_cert`,
:attr:`zookeeper.tls_key`, and :attr:`zookeeper.tls_ca` options.  Your
``zuul.conf`` file should look like:

.. code-block::

   [zookeeper]
   hosts=zookeeper1.example.com:2281,zookeeper2.example.com:2281,zookeeper3.example.com:2281
   tls_cert=/etc/zookeeper/ca/certs/client.pem
   tls_key=/etc/zookeeper/ca/keys/clientkey.pem
   tls_ca=/etc/zookeeper/ca/certs/cacert.pem
