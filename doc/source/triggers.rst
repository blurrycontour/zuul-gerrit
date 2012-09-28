:title: Triggers

Triggers
========

The process of merging a change starts with proposing a change to be
merged.  Currently Zuul only supports Gerrit as a triggering system.
Zuul's design is modular, so alternate triggering and reporting
systems can be supported.  However, Gerrit has a particularly robust
data model, and Zuul does make some assumptions that include that data
model.  Nonetheless, patches to support alternate systems are welcome.

Gerrit
------

Zuul works with standard versions of Gerrit by invoking the ``gerrit
stream-events`` command over an SSH connection.  It also reports back
to Gerrit using SSH.

Gerrit Configuration
~~~~~~~~~~~~~~~~~~~~

Zuul will need access to a Gerrit user.  Consider naming the user
*Jenkins* so that developers see that feedback from changes is from
Jenkins (Zuul attempts to stay out of the way of developers, most
shouldn't even need to know it's there).

Create an SSH keypair for Zuul to use if there isn't one already, and
create a Gerrit user with that key::

  cat ~/id_rsa.pub | ssh -p29418 gerrit.example.com gerrit create-account --ssh-key - --full-name Jenkins jenkins

Give that user whatever permissions will be needed on the projects you
want Zuul to gate.  For instance, you may want to grant ``Verified
+/-1`` and ``Submit`` to the user.  Additional categories or values may
be added to Gerrit.  Zuul is very flexible and can take advantage of
those.

Zuul merges the change to the latest master in the remote repository
then create a new reference for it under ``refs/zuul/*`` and push
it to the remote Gerrit server. Thus you will need to grant jenkins
user the *Create Reference* right on ``refs/zuul/*``.
