OpenID Connect Integration Examples
===================================

This document lists simple How-Tos to help administrators enable OpenID
Connect authentication in Zuul and Zuul's Web UI.

.. toctree::
   :maxdepth: 1

   openid-with-google
   openid-with-keycloak

Debugging
---------

If problems appear:

* Make sure your configuration is correct, especially callback URIs.
* More information can be found in Zuul's web service logs.
* From the user's side, activating the web console in the browser can be helpful
  to debug API calls.
