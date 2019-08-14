:title: Test Jobs And Roles

.. _test-jobs:

Test Jobs And Roles
===================

The following sections describe the best practices to test jobs content.
To ensure changes to a job does not break project using that job, it is
important to define a test job to test the job content.

Local Job
---------

For a local job used by the project the job is defined in, job content
changes should already been tested before being merged.


Tenant Shared Job
-----------------

For a job named `org-test` defined in a `org-jobs` repository that is used by
other project from the tenant, such job can be defined to test the job content
change:

.. code-block:: yaml

   # org-jobs/zuul.d/job-tests.yaml
   ---
   - job:
       name: test-org-test
       parent: org-test
       match-on-config-updates: true
       run: playbooks/test-org-test.yaml
       files:
         - ^roles/org-test-role.*$

   - project:
       check:
         jobs:
           - test-org-test


Then the run phase of this job will run on change to the job definition as well
as changed to the job's role. The playbook can be written such as:

.. code-block:: yaml

   # org-jobs/playbooks/test-org-test.yaml
   ---
   - hosts: all
     tasks:
       - name: Prepare mock data
         command: touch test

       - name: Run the role or playbook
         include_role:
           name: org-test-role

       - name: Assert role worked as expected
         assert:
           that:
             - true


Generic Job
-----------

For project hosting jobs to be used by foreign tenant, the project should not
define a `project` configuration as the other tenant may not have the correct
pipeline and testing should only happen on the tenant that is gating the project.

If the `org-jobs` repository is meant to be shared by multiple tenant, then
the test-org-test definition shouldn't be set in the global zuul.yaml.
Instead, the tenant responsible of testing will load the `org-jobs` project
using this tenant configuration:

.. code-block:: yaml

   # /etc/zuul/main.yaml
   ---
   - tenant:
       name: org-main
       source:
         connection:
           untrusted-projects:
             - org-jobs:
                 extra-config-paths:
                   - zuul-org-tests.d/

   - tenant:
       name: other-tenant
       source:
         connection:
           untrusted-projects:
             - org-jobs

Then the `zuul.d/job-tests.yaml` needs to be stored in
`zuul-org-tests.d/job-tests.yaml` so that only one tenant run the testing job.
