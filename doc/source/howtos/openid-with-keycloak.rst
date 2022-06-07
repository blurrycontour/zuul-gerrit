Configuring Keycloak Authentication
===================================

This document explains how to configure Zuul and Keycloak in order to enable
authentication in Zuul with Keycloak.

Prerequisites
-------------

* The Zuul instance must be able to query Keycloak over HTTPS.
* Authenticating users must be able to reach Keycloak's web UI.
* Have a realm set up in Keycloak.
  `Instructions on how to do so can be found here <https://www.keycloak.org/docs/latest/server_admin/#configuring-realms>`_ .

By convention, we will assume the Keycloak server's FQDN is ``keycloak``, and
Zuul's Web UI's base URL is ``https://zuul/``. We will use the realm ``my_realm``.

Most operations below regarding the configuration of Keycloak can be performed through
Keycloak's admin CLI. The following steps must be performed as an admin on Keycloak's
GUI.

Setting up Keycloak
-------------------

Create a client
...............

Choose the realm ``my_realm``, then click ``clients`` in the Configure panel.
Click ``Create``.

Name your client as you please. We will pick ``zuul`` for this example. Make sure
to fill the following fields:

* Client Protocol: ``openid-connect``
* Access Type: ``public``
* Implicit Flow Enabled: ``ON``
* Valid Redirect URIs: ``https://zuul/*``
* Web Origins: ``https://zuul/``

Click "Save" when done.

Create a client scope
......................

Keycloak maps the client ID to a specific claim, instead of the usual `aud` claim.
We need to configure Keycloak to add our client ID to the `aud` claim by creating
a custom client scope for our client.

Choose the realm ``my_realm``, then click ``client scopes`` in the Configure panel.
Click ``Create``.

Name your scope as you please. We will name it ``zuul_aud`` for this example.
Make sure you fill the following fields:

* Protocol: ``openid-connect``
* Include in Token Scope: ``ON``

Click "Save" when done.

On the Client Scopes page, click on ``zuul_aud`` to configure it; click on
``Mappers`` then ``create``.

Make sure to fill the following:

* Mapper Type: ``Audience``
* Included Client Audience: ``zuul``
* Add to ID token: ``ON``
* Add to access token: ``ON``

Then save.

Finally, go back to the clients list and pick the ``zuul`` client again. Click
on ``Client Scopes``, and add the ``zuul_aud`` scope to the ``Assigned Default
Client Scopes``.

(Optional) Set up a social identity provider
............................................

Keycloak can delegate authentication to predefined social networks. Follow
`these steps to find out how. <https://www.keycloak.org/docs/latest/server_admin/index.html#social-identity-providers>`_

If you don't set up authentication delegation, make sure to create at least one
user in your realm, or allow self-registration. See Keycloak's documentation section
on `user management <https://www.keycloak.org/docs/latest/server_admin/index.html#assembly-managing-users_server_administration_guide>`_
for more details on how to do so.

Setting up Zuul
---------------

Edit the ``/etc/zuul/zuul.conf`` to add the keycloak authenticator:

.. code-block:: ini

   [auth keycloak]
   default=true
   driver=OpenIDConnect
   realm=my_realm
   issuer_id=https://keycloak/auth/realms/my_realm
   client_id=zuul

Restart Zuul services (scheduler, web).

Head to your tenant's status page. If all went well, you should see a "Sign in"
button in the upper right corner of the page. Congratulations!

Further Reading
---------------

This How-To is based on `Keycloak's documentation <https://www.keycloak.org/documentation.html>`_,
specifically `the documentation about clients <https://www.keycloak.org/docs/latest/server_admin/#assembly-managing-clients_server_administration_guide>`_.
