==============
Zuul V3 Update
==============

It's Alive!
===========

* OpenStack Infra running one that tests Zuul patches
* IBM BonnyCI service
* RH Software Factory Integration Patches Written

Major Changes
=============

* In-repo Config
* Shareable Job Config
* Self-testing Job Changes
* Job Inheritance
* Multi-tenant secret system
* Ansible-based Job Content
* Native Multi-node
* Git repo push
* Finger-based log streaming
* Python3 Only

What's Missing?
===============

* Documentation
* Base Job Content
* Cross-driver dependencies
* Web Polish

  * Land Websockets Log Streaming
  * Land Tristan's Dashboard

* Possible breaking bugfixes as we write jobs and docs

In-Repo Config
==============

Two types of repos:

* config repos (trusted)
* project repos (untrusted)

Zuul Tenant Config

Shareable Job Config
====================

* Config is via git repo - can be directly shared

  * openstack-infra/zuul-jobs

    * Base jobs for everyone - other installs should put
      openstack-infra/zuul-jobs in their tenant.yaml
    * tox-py27
    * autotools
    * go-test

  * openstack-infra/openstack-zuul-jobs

    * Jobs specific to OpenStack projects

/etc/zuul/zuul.conf
===================

.. code-block:: ini

  [scheduler]
  tenant_config=/etc/zuul/tenant.yaml

  [connection examplegerrit]
  driver=gerrit
  server=review.example.com

  [connection examplegithub]
  driver=github
  api_token=
  webhook_token=

  [connection exampleghe]
  driver=github
  server=github-enterprise.example.com
  api_token=
  webhook_token=

/etc/zuul/tenant.yaml
=====================

.. code-block:: yaml

  - tenant:
      name: openstack
      source:
        gerrit:
          config-projects:
            - openstack-infra/project-config
          untrusted-projects:
            - openstack-infra/zuul-jobs
            - openstack-infra/openstack-zuul-jobs
            - openstack-infra/nodepool
            - openstack-infra/zuul

Pipeline Config
===============

.. code-block:: yaml

  - pipeline:
      name: check
      manager: independent
      trigger:
        gerrit:
          - event: patchset-created
          - event: comment-added
            comment: (?i)^(Patch Set [0-9]+:)?( [\w\\+-]*)*(\n\n)?\s*recheck
      success:
        gerrit:
          verified: 1
      failure:
        gerrit:
          verified: -1

openstack-infra/zuul-jobs/zuul.yaml - jobs
==========================================

.. code-block:: yaml

  - job:
      name: base
      description: |
        The base job for OpenStack's installation of Zuul.
      pre-run: playbooks/base/pre
      post-run: playbooks/base/post
      roles:
        - zuul: openstack-infra/openstack-zuul-roles
      timeout: 1800
      nodes:
        - name: ubuntu-xenial
          label: ubuntu-xenial

  - job:
      name: unittests
      parent: base
      description: |
        Perform setup common to all unit test jobs.
      roles:
        - zuul: openstack-infra/zuul-jobs
      pre-run: playbooks/unittests/pre

  - job:
      name: tox
      parent: unittests
      run: playbooks/tox/run
      pre-run: playbooks/tox/pre
      post-run: playbooks/tox/post
  
  - job:
      name: tox-linters
      parent: tox
      vars:
        tox_environment: linters
  
openstack-infra/zuul-jobs/zuul.yaml - project
=============================================

.. code-block:: yaml

  - project:
      name: openstack-infra/zuul-jobs
      check:
        jobs:
          - tox-linters

openstack-infra/zuul/.zuul.yaml
===============================

.. code-block:: yaml

  - project:
      name: openstack-infra/zuul
      check:
        jobs:
          - tox-linters

Job Variants
============

* Allow users to override pieces of jobs

.. code-block:: yaml

  # openstack-infra/zuul/.zuul.yaml
  - job:
      name: tox-linters
      branch: stable/newton
      nodes:
        - name: centos-7
          label: centos-7

  - project:
      name: openstack-infra/zuul-jobs
      check:
        jobs:
          - tox-linters

Self-testing Job Changes
========================

.. container:: progressive

  * Job config changes in untrusted repos are live-applied to their change
  * Speculative job changes apply across depends-on boundries
  * What? -- https://review.openstack.org/#/c/480692/

Depends-On
==========

* Not new - but worth noting
* git footer that allows one change to "depend" on another
* zuul will not merge a change before its depends have landed
* zuul will test dependent changes as-if the change they depend on has landed
* Works across multiple repositories
* Works in the same repository

Same Repo Depends-On
====================

* Patch Stacks are unpossible in GitHub

  * PR 1 with patch A
  * PR 2 with patch A and B
  * PR 2 shows diff containing A and B
  * Muddies review of interelated but separate thoughts

* Depends-On in the same repo

  * PR 1 with patch A
  * PR 2 with patch B Depends-On: PR 1
  * PR 1 shows diff of patch A
  * PR 2 shows diff of patch B

* Doesn't always work - sometimes the git relationship is too close

Upcoming Changes to Depends-On
==============================

Today:

* Gerrit: Depends-On: I813f3f2ae138c07918556bc81655518023527131
* GitHub: Depends-On: https://github.com/j2sol/z8s-sandbox/pull/1

Tomorrow:

* Gerrit: Depends-On: https://review.openstack.org/#/c/478265/
* Gerrit: Depends-On: https://github.com/j2sol/z8s-sandbox/pull/1
* GitHub: Depends-On: https://review.openstack.org/#/c/478265/
* GitHub: Depends-On: https://github.com/j2sol/z8s-sandbox/pull/1

Ansible Job Content
===================

* Job Inheritance
* Composition via Ansible Roles
* Jobs have playbooks for:

  * pre-run
  * run
  * post-run

* pre-run failures trigger retries
* post-run always run
* pre/post playbooks in inheritance run in "Onion" fashion

  * base pre
  * unittest pre
  * tox pre
  * tox run
  * tox post
  * unittest post
  * base post

Trusted vs. Untrusted
=====================

* All ansible execution is wrapped with bubblewrap
* Untrusted jobs also have restrictions via action plugins
* Trusted jobs have access to executor filesystem
* Trusted jobs are not applied speculatively

GitHub Support
==============

Two different integration options

# Register as "App" on GitHub and add App to Repo

  * https://github.com/apps/openstack-zuul

# Use "webhooks" on a Repo

* Triggers on Events

  * pull_request
  * pull_request_review
  * push

* Reporters:

  * GitHub PR status
  * Pull-Request Comment
  * Label
  * Merge Change

GitHub Events
=============

pull_request

* opened
* changed
* closed
* reopened
* comment
* labeled
* unlabled
* status

pull_request_review

* submitted
* dismissed

First-class Multi-Node
======================

* Nodes are given to jobs in Ansible Inventory
* https://review.openstack.org/#/c/481014/

.. code-block:: yaml

  - nodeset:
      name: ceph-cluster
      nodes:
        - name: controller
          label: ubuntu-xenial
        - name: compute1
          label: ubuntu-xenial
        - name: compute2
          label: ubuntu-xenial
      groups:
        - name: ceph-osd
          nodes:
            - controller
        - name: ceph-monitor
          nodes:
            - controller
            - compute1
            - compute2

  - job:
      parent: base
      name: ceph-multinode
      nodes: ceph-cluster

Job Config Error Reporting
==========================

* Speculative job config syntax checking

https://review.openstack.org/#/c/481014/1

Git Repos Pushed to Nodes
=========================

* ansible-playbook runs on Executors
* job content runs on Nodes
* zuul prepares git repo state on executor
* base job pushes git repo content to all nodes
* golang source repo structure used

.. code-block:: bash

  src/git.openstack.org/openstack-infra/zuul
  src/github.com/ansible/ansible

* Working dir is $HOME
* Project under test is {{ zuul.project.canonical_name }}

.. code-block:: yaml

  - name: Run tox
    args:
      chdir: "src/{{ zuul.project.canonical_name }}"
    shell: "tox {{ tox_environment }}"

Things we didn't get to but are done
====================================

* Multi-tenancy
* Secrets

Short to Medium Term Next Steps
===============================

* Land Websockets Log Streaming
* Finish porting OpenStack "base" content
* Finish writing docs
* Add GitHub App "OpenStack Zuul" to github.com/ansible/ansible
* Add jobs to cross-test ansible/ansible and openstack-infra/zuul
* Add jobs to cross-test ansible:cloud/openstack and openstack-infra/shade
* Add FedMsg/MQTT Triggers/Reporters

  * Paul Belanger has much of this already done - deferring for prioritization

* Add Static Node support to Nodepool

  * Tristan has much of this already done

* Zuul Dashboard
* Linch-Pin Nodepool driver
