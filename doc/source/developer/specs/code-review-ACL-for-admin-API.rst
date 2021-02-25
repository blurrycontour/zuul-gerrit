===================================
External ACLs for the admin web API
===================================

The aim of this spec is to extend the current access control rules in the admin
web API.

Problem description
===================

Access to the admin web API is controlled by admin rules. These rules are defined
as a set of basic conditions on the claims in a user's token. That token, or JWT,
is issued to the user by an Identity Provider following the OpenID Connect protocol;
thus the claims reflect how a user is defined in the Identity Provider, especially
regarding the groups she belongs to or the roles she is granted.

While the idea behind adding OpenID Connect-based authentication and authorization
to Zuul was to provide a "single sign on" experience for users from the code review
system to the CI and gating service and access to a single source of truth regarding
who a user is and what they can do, it appears that most code review systems implement their own
access rules and seldom rely on Identity Providers' data for authorization. It would
be easier for tenant administrators to apply access rules and permissions as they
are defined on the code review systems defined as sources for the tenant.

Proposed Change
===============

Each source driver, when relevant, will provide an interface to check a user's
permissions on that source. It is assumed that the same authentication system is
shared between Zuul and the given source, ie an authenticated user on Zuul can be
looked up on the source by her username.

Source permission-checking will be enabled by default, and classic claims-based
admin rules will be allowed to override this check. This is meant to avoid unnecessary
back-and-forths between Zuul and the source, as external permissions will only be
checked if the user's claims don't match Zuul-defined admin rules.

External permission checking will also be silently discarded if the source driver's
configuration doesn't allow access to this information.

Rules will be hard-coded, first to reflect the intended rules of the external sources,
and so that this feature is as transparent as possible for operators.

Note that sources define permissions at repository level, whereas Zuul's
admin rules are applied at tenant level.

Gerrit
------

Gerrit permissions are complex, a simple and generic approach would be to grant
privileges to users who:

* have access to the project's `refs/meta/config` ref, or
* can set a "Code-Review" label to -2 or +2 on changes (`refs/heads/*`), or
* are owners of the project's `refs/*`.

This assumes a somewhat standard deployment of Gerrit.

REST API
........

If Zuul is given the View Access global capability, the following endpoint can be
checked for user permissions: https://review.opendev.org/Documentation/rest-api-projects.html#check-access

If not, the access endpoint may be used to fetch the relevant groups: https://gerrit-review.googlesource.com/Documentation/rest-api-projects.html#get-access
It is then possible to check the membership of a user in each of these groups by using
the following endpoint: https://gerrit-review.googlesource.com/Documentation/rest-api-groups.html#group-members

SSH CLI
.......

Visible refs for a user on a project can be listed this way:

.. code-block:: shell

  ssh -p 29418 -i /var/lib/zuul/.ssh/id_rsa zuul@gerrit gerrit ls-user-refs -p myproject -u user

However the ssh user must be an administrator to be allowed to use `ls-user-refs`.

It does not seem possible to find out whether a user is the project's owner, or
whether she can set the CR label to -2/+2, via the SSH CLI.

Github
------

Github handles access control on projects as "permissions". There are four different
levels of permissions on a given project: `admin`, `write`, `read` or `none`.

According to `Github's API documentation <https://docs.github.com/en/rest/reference/projects#get-project-permission-for-a-user>`_,
the following endpoint can be reached by a Github App to check the permissions:

.. code-block:: shell

  https://api.github.com/repos/:owner/:repository/collaborators/:username/permission

By default, users with a permission of ``admin`` on the repository will be allowed
to perform admin actions with Zuul's REST API.

Gitlab
------

Gitlab handles access control on projects as `"access levels" <https://docs.gitlab.com/ee/api/members.html#valid-access-levels>`_.

By default, users with an access level higher than 40 (Maintainer and Owner) will
be allowed to perform admin actions with Zuul's REST API.

`Gitlab's API <https://docs.gitlab.com/ee/api/members.html#list-all-members-of-a-group-or-project-including-inherited-members>`_
provides an endpoint to retrieve members of a project and their access level.

In order to avoid an extra call to the API to find the user ID of the authenticated
user prior to querying members, Zuul will get all members and filter the results
by the username of the authenticated user.


Pagure
------

`Pagure can provide access information to a project via its API. <https://pagure.io/api/0/#projects-tab>`_
There are 5 access levels: `admin`, `collaborator`, `commit`, `owner` and `ticket`.

By default, users with an access level of admin or owner will be allowed to perform
admin actions with Zuul's REST API.

The levels can be granted directly to a user, or to a group, as seen in this
example:

.. code-block:: javascript

  {
    "access_groups": {
      "admin": [],
      "commit": [],
      "ticket": []
    },
    "access_users": {
      "admin": [
        "ryanlerch"
      ],
      "commit": [
        "puiterwijk"
      ],
      "owner": [
        "pingou"
      ],
      "ticket": [
        "vivekanand1101",
        "mprahl",
        "jcline",
        "lslebodn",
        "cverna",
        "farhaan"
      ]
    },
    "close_status": [
      "Invalid",
      "Insufficient data",
      "Fixed",
      "Duplicate"
    ],
    "custom_keys": [],
    "date_created": "1431549490",
    "date_modified": "1431549490",
    "description": "A git centered forge",
    "fullname": "pagure",
    "id": 10,
    "milestones": {},
    "name": "pagure",
    "namespace": null,
    "parent": null,
    "priorities": {},
    "tags": [
      "pagure",
      "fedmsg"
    ],
    "user": {
      "fullname": "Pierre-YvesChibon",
      "name": "pingou"
    }
  }

In the best case scenario, one API call to Pagure will be enough to check a user's
access level. In the worst case scenario, every group with admin access level must
be checked for user membership. A patch to Pagure's API to implement direct membership checks
could be proposed.

Implementation
==============

Impact
------

This feature may have performance impacts for the following reasons:

* More external calls to sources will be required in order to fetch a user's permissions.
  User-triggered actions *should* be rare enough that it should be negligible.
* In the current implementation of the admin web UI, a dequeue button is displayed near a
  change on the status page if the user is a tenant admin, invisible otherwise. Since 
  external permissions are at the repository level, a check would be necessary for each
  project with an item on the status page before displaying the button. With large Zuul setups,
  this could bring the GUI to a halt and hammer the connections with an unreasonable amount of API calls.
  A simple workaround could be to display the dequeue button at all times when a user is authenticated, 
  check the permissions only when the dequeue is actually triggered, and display an error message when
  attempting to dequeue a change without the right permissions.

Expected changes that should not impact performances:

* The connection info must be added to a change object, especially in the GUI. This
  will make ACL lookups possible this way.

Documentation
-------------

* The default permission behavior per connection type will be added to the administrator
  documentation.
* The requirements on the connection configuration will be updated in the documentation
  if necessary.

Security
--------

* In order to access a user's permissions, most sources require that the API query
  be done with elevated rights on a given project. Since merge privileges are
  already required, existing rights should be sufficient, but might need to be
  altered, like for example ensuring that Zuul's Gerrit account as the Access View
  capability.
* It is assumed both Zuul and the source use matching identity providers, so that
  a user authenticated in Zuul can be looked up on the source by their username.
  If this is not the case, this may allow user impersonation if a user in Zuul's
  identity provider is defined with a username that exists in github, for example.

Testing
-------

* Mock testing of the permission queries will be added for each relevant source driver.

Follow-up Work
--------------

* Given that several API calls may be necessary per permission check, this feature
  is a good candidate for caching.
* It might be an opportunity to add project-level ACLs in addition to existing tenant-level ones.