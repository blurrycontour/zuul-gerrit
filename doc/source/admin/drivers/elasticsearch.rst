:title: Elasticsearch Driver

Elasticsearch
=============

The Elasticsearch driver supports reporters only.

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

   .. attr:: index
      :default: ''

      The Elasticsearch index Zuul will create and use to index build and
      buildset results.

Reporter Configuration
----------------------

This reporter is used to store results in a Elasticsearch index.

For example:

.. code-block:: yaml

   - pipeline:
       name: check
       success:
         elasticsearch:
       failure:
         elasticsearch:
           index_jobs_vars: True
