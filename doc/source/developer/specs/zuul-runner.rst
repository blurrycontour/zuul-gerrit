Zuul Runner
===========

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

While Zuul can be deployed to reproduce a job locally, it
is a complex enough system to setup. Zuul jobs being written in
Ansible, we shouldn't have to setup a Zookeeper, Nodepool and Zuul
service to run a job locally.

To that end, the Zuul Project should create a command line utility
to run a job locally using direct ansible-playbook commands execution.

Zuul Job Execution Context
--------------------------

One of the key parts of making the Zuul Runner command line utility
is to reproduce as close as possible the zuul service environment.

A Zuul jobs requires:

- Test resources
- Copies of the required projects
- Ansible configuration
- Decrypted copies of the secrets


Test Resources
~~~~~~~~~~~~~~

The Zuul Runner shall requires the user to provide test resources.
The simplest usage would be to let the user provide an Ansible inventory.
The user could also provides a nodepool.yaml and the zuul-runner cli
using an inlined Nodepool object as proposed in:
https://review.opendev.org/#/c/639632/

Required Projects
~~~~~~~~~~~~~~~~~

The Zuul Runner shall queries an existing Zuul API to get the list
of projects required to run a job. This is implemented as part of
the `topic:freeze_job` changes to expose the executor gearman parameters.

The CLI would then perform the executor service task to clone and merge
the required project locally.

Ansible Configuration
~~~~~~~~~~~~~~~~~~~~~

The CLI would also perform the executor service tasks to setup the
execution context.

Secrets
~~~~~~~

The Zuul Runner shall requires the user to provide his own copies of
any secrets required by the job.


Implementation
--------------

The process of exposing gearman parameter and refactoring the executor
code to support local/direct usage already started here:
https://review.opendev.org/#/q/topic:freeze_job+(status:open+OR+status:merged)


Zuul Runner CLI
---------------

Here is the proposed usage for the CLI:

.. code-block:: shell

   usage: zuul-runner [-h] [-c CONFIG] [--version] [-v] [-e FILE] [-a API]
                      [-t TENANT] [-j JOB] [-P PIPELINE] [-p PROJECT] [-b BRANCH]
                      [-g GIT_DIR] [-D DEPENDS_ON]
                      {prepare-workspace,execute} ...

   A helper script for running zuul jobs locally.

   optional arguments:
     -h, --help            show this help message and exit
     -c CONFIG             specify the config file
     --version             show zuul version
     -v, --verbose         verbose output
     -e FILE, --extra-vars FILE
                           global extra vars file
     -a API, --api API     the zuul server api to query against
     -t TENANT, --tenant TENANT
                           the zuul tenant name
     -j JOB, --job JOB     the zuul job name
     -P PIPELINE, --pipeline PIPELINE
                           the zuul pipeline name
     -p PROJECT, --project PROJECT
                           the zuul project name
     -b BRANCH, --branch BRANCH
                           the zuul project's branch name
     -g GIT_DIR, --git-dir GIT_DIR
                           the git merger dir
     -D DEPENDS_ON, --depends-on DEPENDS_ON
                           reproduce job with speculative depends-on

   commands:
     valid commands

     {prepare-workspace,execute}
       prepare-workspace   checks out all of the required playbooks and roles
                           into a given workspace and returns the order of
                           execution
       execute             prepare and execute a zuul jobs


And here is an example execution:

.. code-block:: shell

   $ pip install --user zuul
   $ zuul-runner --api https://zuul.openstack.org --project openstack/nova \
       --job tempest-full-py3 execute --nodes ssh:rhel8:instance-ip:tdecacqu:/home/tdecacqu
   [...]
   2019-05-07 06:08:01,040 DEBUG zuul.Runner - Ansible output: b'PLAY RECAP *********************************************************************'
   2019-05-07 06:08:01,040 DEBUG zuul.Runner - Ansible output: b'instance-ip                : ok=9    changed=5    unreachable=0    failed=0'
   2019-05-07 06:08:01,040 DEBUG zuul.Runner - Ansible output: b'localhost                  : ok=12   changed=9    unreachable=0    failed=0'
   2019-05-07 06:08:01,040 DEBUG zuul.Runner - Ansible output: b''
   2019-05-07 06:08:01,218 DEBUG zuul.Runner - Ansible output terminated
   2019-05-07 06:08:01,219 DEBUG zuul.Runner - Ansible cpu times: user=0.00, system=0.00, children_user=0.00, children_system=0.00
   2019-05-07 06:08:01,219 DEBUG zuul.Runner - Ansible exit code: 0
   2019-05-07 06:08:01,219 DEBUG zuul.Runner - Stopped disk job killer
   2019-05-07 06:08:01,220 DEBUG zuul.Runner - Ansible complete, result RESULT_NORMAL code 0
   2019-05-07 06:08:01,220 DEBUG zuul.ExecutorServer - Sent SIGTERM to SSH Agent, {'SSH_AUTH_SOCK': '/tmp/ssh-SYKgxg36XMBa/agent.18274', 'SSH_AGENT_PID': '18275'}
   SUCCESS
