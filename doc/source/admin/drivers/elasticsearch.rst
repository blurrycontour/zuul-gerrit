:title: Elasticsearch Driver

Elasticsearch
=============

The Elasticsearch driver supports reporters only. The purpose of the driver is
to export build and buildset results to an Elasticsearch index. If the
index does not exist in Elastic then the driver will create it with an
appropriate mapping.

The driver adds job's variables to exported build doc into the `job_vars` field.
Furthermore any data returned to Zuul via zuul_return will be added into
the field `job_returned_vars`. Elasticsearch supports a number of different
datatypes for the fields in a document. Please refer to its `documentation`_.

.. _documentation: https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-types.html

Connection Configuration
------------------------

The connection options for the Elasticsearch driver are:

.. attr:: <Elasticsearch connection>

   .. attr:: driver
      :required:

      .. value:: elasticsearch

         The connection must set ``driver=elasticsearch``.

   .. attr:: uri
      :required:

      Database connection information in the form of a comma separated
      list of ``host:port``.

      Example: elasticsearch1.domain:9200,elasticsearch2.domain:9200

   .. attr:: use_ssl
      :default: false

      Turn on SSL.

   .. attr:: verify_certs
      :default: false

      Make sure we verify SSL certificates.

   .. attr:: ca_certs
      :default: ''

      Path to CA certs on disk.

   .. attr:: client_cert
      :default: ''

      Path to the PEM formatted SSL client certificate.

   .. attr:: client_key
      :default: ''

      Path to the PEM formatted SSL client key.

   .. attr:: index
      :default: ''

      The Elasticsearch index Zuul will create and use to index build and
      buildset results.

Reporter Configuration
----------------------

This reporter is used to store build results in an Elasticsearch index.

The Elasticsearch reporter does nothing on :attr:`pipeline.start` or
:attr:`pipeline.merge-failure`; it only acts on
:attr:`pipeline.success` or :attr:`pipeline.failure` reporting stages.

.. attr:: pipeline.<reporter>.<elasticsearch source>
