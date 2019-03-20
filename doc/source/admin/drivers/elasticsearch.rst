:title: Elasticsearch Driver

Elasticsearch
=============

The Elasticsearch driver supports reporters only. The purpose of the driver is
to export build and buildset results to an Elasticsearch index. If the
index does not exist in Elastic then the driver will create it with an
appropriate mapping.

Optionaly the driver can also add job's variables to build results. In case
the job's variables are configured to be indexed and a job uses zuul_return to
return a dict such as ``{vars_overwrite: {}}`` to Zuul then the vars_overwrite
content overwrites original jobs's variables.


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

   The following attributes are supported:

   .. attr:: job-vars
      :default: []

      If set then job's variables will be indexed along with the build object.
      This accepts a list of regexes. Only variables matching one of the
      provided regexes will indexed.
