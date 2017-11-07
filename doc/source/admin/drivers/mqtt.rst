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


Reporter Configuration
----------------------

A :ref:`connection<connections` that uses the mqtt driver must be supplied to the
reporter. Each pipeline must provide a topic name. For example:

.. code-block:: yaml

   - pipeline:
       name: check
       success:
         mqtt:
           topic: zuul_buildset

.. attr:: pipeline.<reporter>.<mqtt>

   To report via MQTT message, the dictionaries passed to any of the pipeline
   :ref:`reporter<reporters>` support the following attributes:

   .. attr:: topic

      The MQTT topic to publish message.
