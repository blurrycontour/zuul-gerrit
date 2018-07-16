:title: Job logs

.. _zuul-artifacts-export:

Export logs artifacts to the logserver
--------------------------------------

After a job ran, Zuul base job may exports the job's *console* log to
a log server.

When a job generate extra artifacts, such as log files, a *post-run* playbook
can be written to export the artifacts to *zuul.executor.log_root*.

An example of a *fetch-logs.yaml* playbook.

.. code-block:: yaml

 ---
 - hosts: all
   tasks:
     - name: Upload logs
       synchronize:
         src: '{{ zuul.project.src_dir }}/logs'
         dest: '{{ zuul.executor.log_root }}'
         mode: pull
         copy_links: true
         verify_host: true
         rsync_opts:
           - --include=/logs/**
           - --include=*/
           - --exclude=*
           - --prune-empty-dirs

A job can use that playbook as *post-run* then each files
in the *zuul.project.src_dir/logs/* will be exported to the log server.

.. code-block:: yaml

  ---
  - job:
      name: build
      parent: base
      description: My job
      run: playbooks/run.yaml
      post-run: playbooks/fetch-logs.yaml


.. _zuul-artifacts-export-logstash:

Export logs artifacts to logstash
---------------------------------

A job can be configured to export specific artifacts
to logstash to make them available to the search via Kibana.

The job variable *logstash_processor_config* need to be provided
as follow:

.. code-block:: yaml

  ---
  - job:
      name: build
      parent: base
      description: My job
      run: playbooks/run.yaml
      post-run:
        - playbooks/fetch-logs.yaml
      vars:
        logstash_processor_config:
          files:
            - name: logs/.*\.log
            - name: job-output\.txt
              tags:
                - console
                - console.html

With this definition, zuul will export all the generated artifacts
located in the *logs/* directory to logstash. The *logstash_processor_config*
variable definition overwrites the one from the base job,
that's why, the *job-output.log* (console) must specified too.
