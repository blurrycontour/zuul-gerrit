:title: URL Driver

URL
===

The driver supports triggers only. It is used for configuring
pipelines so that jobs run when a the resource located at an URL
has changed. No connection configuration is required.

Trigger Configuration
---------------------

This trigger will run based on a cron-style time specification. At
each run the driver requests the resource HTTP headers and evaluate
whether the resource state has changed. If changed it will enqueue
an event into its pipeline for every project defined in
the configuration. Any job associated with the pipeline will run in
response to that event.

To evaluate if a resource state has changed, the driver keeps a cache
of the header's field value. When the cache is empty then the cache is
filled with the value but no event is enqueued. If the previous value
in the cache changed then event is enqueued in the pipeline.

.. attr:: pipeline.trigger.url

   The url trigger supports the following attributes:

   .. attr:: time
      :required:

      The time specification in cron syntax.  Only the 5 part syntax
      is supported, not the symbolic names.  Example: ``0 0 * * *``
      runs at midnight. The first weekday is Monday.

   .. attr:: url
      :required:

      The url where the resource is located.

   .. attr:: header_field
      :required:

      The HTTP header field to evaluate.
