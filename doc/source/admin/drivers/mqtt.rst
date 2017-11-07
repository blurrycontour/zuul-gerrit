:title: MQTT Driver

MQTT
====

The MQTT driver supports reporters only. It is used to send MQTT
message when items report.

Connection Configuration
------------------------

.. attr:: <mqtt connection>

   .. attr:: driver
      :required:

      .. value:: mqtt

         The connection must set ``driver=mqtt`` for MQTT connections.

   .. attr:: server
      :default: localhost

      MQTT server hostname or address to use.

   .. attr:: port
      :default: 1883

      MQTT server port.

   .. attr:: keepalive
      :default: 60

      Maximum period in seconds allowed between communications with the broker.

   .. attr:: user

      Set a username for optional broker authentication.

   .. attr:: password

      Set a password for optional broker authentication.

   .. attr:: ca_certs

      A string path to the Certificate Authority certificate files to enable
      TLS connection.

   .. attr:: certfile

      A strings pointing to the PEM encoded client certificate to
      enable client TLS based authentication. This option requires keyfile to
      be set too.

   .. attr:: keyfile

      A strings pointing to the PEM encoded client private keys to
      enable client TLS based authentication. This option requires certfile to
      be set too.

   .. attr:: tls_version
      :default: TLSv1

      Specifies the version of the SSL/TLS protocol to be used.
      Available versions are ``TLSv1``, ``TLSv1.1``, ``TLSv1.2``.

   .. attr:: ciphers

      A string specifying which encryption ciphers are allowable for this
      connection. More information in this
      `doc <https://www.openssl.org/docs/manmaster/man1/ciphers.html>`_.


Reporter Configuration
----------------------

A :ref:`connection<connections>` that uses the mqtt driver must be supplied to the
reporter. Each pipeline must provide a topic name. For example:

.. code-block:: yaml

   - pipeline:
       name: check
       success:
         mqtt:
           topic: "{tenant}/zuul/{pipeline}/{project}/{branch}/{change}"
           qos: 2


.. attr:: pipeline.<reporter>.<mqtt>

   To report via MQTT message, the dictionaries passed to any of the pipeline
   :ref:`reporter<reporters>` support the following attributes:

   .. attr:: topic

      The MQTT topic to publish messages. The topic can be a format string that
      can use the following parameters: ``tenant``, ``pipeline``, ``project``,
      ``branch``, ``change``, ``patchset`` and ``ref``.
      MQTT topic can have hierarchy separated by ``/``, more details in this
      `doc <https://mosquitto.org/man/mqtt-7.html>`_

   .. attr:: qos
      :default: 0

      The quality of service level to use, it can be 0, 1 or 2. Read more in this
      `guide <https://www.hivemq.com/blog/mqtt-essentials-part-6-mqtt-quality-of-service-levels>`_
