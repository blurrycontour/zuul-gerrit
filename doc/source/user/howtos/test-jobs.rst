:title: Test Jobs And Roles

.. _test-jobs:

Test Jobs And Roles
===================

The following sections describe the best practices to test jobs content.
To ensure changes to a job do not break project using that job, it is
important to define a test job to test the job content.

Local Job
---------

For a local job used by the project the job is defined in, job content
changes are already being tested before being merged.


Tenant Shared Job
-----------------

For a job named `org-job` defined in a `org-jobs` repository that is used by
other projects from the tenant, a new job can be defined to test the job content:


.. code-block:: yaml

   # org-jobs/zuul.d/job-tests.yaml
   ---
   - job:
       name: test-org-job
       parent: org-job
       match-on-config-updates: true
       run: playbooks/test-org-job.yaml
       files:
         - ^roles/org-job-role.*$
         - ^playbooks/org-job.yaml

   - project:
       check:
         jobs:
           - test-org-job


Then the run phase of this job validates changes to the job definition as well
as changes to the job's role. The playbook can be written such as:

.. code-block:: yaml

   # org-jobs/playbooks/test-org-job.yaml
   ---
   - hosts: all
     tasks:
       - name: Prepare mock data
         command: touch test

       - name: Run the role or playbook
         include_role:
           name: org-job-role

       - name: Assert role worked as expected
         assert:
           that:
             - true


Generic Job
-----------

For project hosting jobs to be used by foreign tenants, the project should not
define a `project` configuration as the other tenants may not have the correct
pipelines and testing should only happen on the tenant that is gating the project.

When the `org-jobs` repository is meant to be shared by multiple tenants, then
the test-org-job definition should not be set in the global zuul.yaml.
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

Note that the other tenants may have different base jobs and the environment,
such as mirror_info, may be different. The test-org-job content needs to
simulate as much as possible how the job/role is supposed to be used.


Third Party Ci Test Job
-----------------------

As a foreign tenant, a job can be defined to provide third party CI results
to the tenant hosting the jobs.

.. code-block:: yaml

   # other-tenant-jobs/zuul.d/org-third-party-ci.yaml
   ---
   - job:
       name: test-org-job-from-other-tenant
       parent: org-job
       match-on-config-updates: true
       run: playbooks/other-org-test.yaml
       files:
         - ^roles/org-job-role.*$
         - ^playbooks/org-job.yaml
       required-projects:
         - org-jobs
       roles:
         - zuul: org-jobs


To add jobs to a foreign project's pipeline, the project definition needs
to be part of a trusted config-project.

.. code-block:: yaml

   # other-tenant-config/zuul.d/projects.yaml
   ---
   - project:
       third-party-checks:
         jobs:
           - test-org-job-from-other-tenant
