:title: Elasticsearch Driver

Elasticsearch
=============

The Elasticsearch driver supports reporters only. The purpose of the driver is
to export build and buildset results to an Elasticsearch index.

If the index does not exist in Elasticsearch then the driver will create it
with an appropriate mapping for static fields.

The driver can add job's variables and any data returned to Zuul
via zuul_return respectively into the `job_vars` and `job_returned_vars` fields
of the exported build doc. Elasticsearch will apply a dynamic data type
detection for those fields.

Elasticsearch supports a number of different datatypes for the fields in a
document. Please refer to its `documentation`_.


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
      :default: true

      Turn on SSL.

   .. attr:: verify_certs
      :default: true

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


Reporter Configuration
----------------------

This reporter is used to store build results in an Elasticsearch index.

The Elasticsearch reporter does nothing on :attr:`pipeline.start` or
:attr:`pipeline.merge-failure`; it only acts on
:attr:`pipeline.success` or :attr:`pipeline.failure` reporting stages.

.. attr:: pipeline.<reporter>.<elasticsearch source>

   The reporter support the following attributes:

   .. attr:: index
      :default: zuul

      The Elasticsearch index to be used to index the data. To prevent
      any name collisions between Zuul tenants, the tenant name is used as index
      name prefix. The real index name will be <index-name>.<tenant-name>.
      The index will be created if it does not exist.

   .. attr:: index-vars
      :default: false

      Boolean value that determines if the reporter should add job's vars
      to the exported build doc.

   .. attr:: index-returned-vars
      :default: false

      Boolean value that determines if the reporter should add zuul_returned
      vars to the exported build doc.
