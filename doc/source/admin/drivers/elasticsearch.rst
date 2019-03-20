:title: Elasticsearch Driver

Elasticsearch
=============

The Elasticsearch driver supports reporters only. Purpose of the driver is
to export build and buildset results to an Elasticsearch index. If the
index does not exist in Elastic then the driver will create it with an
appropriate mapping.

Optionaly the driver can also add job's variables to build results.

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

      Database connection information in the form of a URI understood
      by the Elasticsearch Python client.

      Example: 'elasticsearch.domain:9200'

   .. attr:: index
      :default: ''

      The Elasticsearch index Zuul will create and use to index build and
      buildset results.

Reporter Configuration
----------------------

This reporter is used to store build results in a Elasticsearch index.

The Elasticsearch reporter does nothing on :attr:`pipeline.start` or
:attr:`pipeline.merge-failure`; it only acts on
:attr:`pipeline.success` or :attr:`pipeline.failure` reporting stages.

.. attr:: pipeline.<reporter>.<elasticsearch source>

   The following attributes are supported:

   .. attr:: job_vars_re
      :default: []

      If set then job's variables will be indexed along with the build object
      but only variables matching one of the provided regexps.
