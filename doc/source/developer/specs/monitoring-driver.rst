Generic Metric and Monitoring Interface
=======================================

There has been interest in using prometheus to collect Zuul's metrics and
monitor the services.

In this document, we will consider a refactor to implement a generic
driver interface to support both statsd and prometheus. This interface
shall support both:

* Path based metrics, e.g. zuul.tenant.<tenant>.pipeline.<pipeline>.total
* Name + labels based metrics ,
  e.g. zuul_pipeline_total{tenant=<tenant>, pipeline=<pipeline>}


.. _metric-driver:

Metric driver
-------------

.. code-block:: python

   @abstract
   def metric(type, name, value, description, path_template, **labels):
       ...

* type can be "gauge", "counter"
* name is the metric name, e.g. zuul_pipeline_total
* value is the current metric value
* description is a one-line description of the metric purpose
* path_template is a python string format,
  e.g. zuul.tenant.{tenant}.pipeline.{pipeline}.total
* labels is a dictionary, e.g. {tenant: 'openstack', pipeline: 'check'}


Statsd Implementation
.....................

Statsd implementation pushs statsd to a statsd server.

.. code-block:: python

   statsd.gauge(path_template.format(**labels), value)


Prometheus Implementation
.........................

Prometheus implentation `starts an http server`_ and stores the metrics
in memory. The external prometheus server polls the http endpoint periodically.

.. code-block:: python

   # Metrics object are global
   if name not in self.gl_metrics:
       self.gl_metrics[name] = prometheus.Gauge(
           name, description, list(labels.keys()))
   self.gl_metrics[name].labels(**labels).set(value)


Notes
-----

Based on zuul.conf options, only one implementation may be activated per
service.

See the Prometheus documentation about data-model_ and naming-practice_.

.. _`start an http servers`: https://github.com/prometheus/client_python#three-step-demo
.. _data-model: https://prometheus.io/docs/concepts/data_model/
.. _naming-practice: https://prometheus.io/docs/practices/naming/
