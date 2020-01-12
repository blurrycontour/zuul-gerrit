:title: Badges

.. We don't need no stinking badges

.. _badges:

Badges
======

You can embed a badge declaring that your project is gated and therefore by
definition always has a working build. Since there is only one status to
report, it is a simple static file:

.. image:: https://zuul-ci.org/gated.svg
   :alt: Zuul: Gated

To use it, simply put ``https://zuul-ci.org/gated.svg`` into an RST or
markdown formatted README file, or use it in an ``<img>`` tag in HTML.

For advanced usage Zuul also supports generating dynamic badges via the
REST api. This can be useful if you want to display the status of e.g. periodic
pipelines of a project.

When requesting a list of buildsets while while requesting an image via the
``accept`` header Zuul generates a badge for the first item instead of returning
the list of buildsets. To use it put something like
``https://zuul.opendev.org/api/tenant/zuul/buildsets?project=zuul/zuul-website&pipeline=post``
into an ``<img>`` tag in HTML. The browser will automatically take care of
requesting an image.
