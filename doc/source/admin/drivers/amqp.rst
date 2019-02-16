:title: AMQP Driver

AMQP
====

Advanced Message Queuing Protocol (`AMQP`_) is a message bus.
The AMQP driver only supports triggers.

.. _AMQP: https://www.amqp.org/

Connection Configuration
------------------------

.. attr:: <amqp connection>

   .. attr:: driver
      :required:

      .. value:: amqp

         The connection must set ``driver=amqp`` for AMQP connections.

   .. attr:: urls
      :required:

      The server urls, semicolon separated.

   .. attr:: address
      :required:

      The message address to subscribe to. It may contain the '>' wildcard.

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


Trigger Configuration
---------------------

Zuul works with standard versions of AMQP by subscribing to an address. Message
received can be used to trigger a pipeline based on further filtering:

.. code-block:: yaml

   - pipeline:
       trigger:
         amqp:
           - event: message-published
             address: ^/topic/VirtualTopic.qe.ci.*$
             body:
               type: release
               product: ^os-.*$


.. attr:: pipeline.trigger.<amqp source>

   The dictionary list passed to the AMQP pipeline ``trigger`` attribute
   supports the following attributes:

   .. attr:: event
      :required:

      .. value:: message-published

         Only message-published event are currently supported.

   .. attr:: address

      The address of the message. This field is treated as a
      regular expression, and multiple addresses may be listed.

   .. attr:: body

      A dictionary of expected key/value to be part of the
      message body. Values are treated as a regular expression.
