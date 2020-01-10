Project Definition
==================

.. attr:: project

   The following attributes may appear in a project:

   .. attr:: name

      The name of the project.  If Zuul is configured with two or more
      unique projects with the same name, the canonical hostname for
      the project should be included (e.g., `git.example.com/foo`).
      This can also be a regex. In this case the regex must start with ``^``
      and match the full project name following the same rule as name without
      regex. If not given it is implicitly derived from the project where this
      is defined.

   .. attr:: templates

      A list of :ref:`project-template` references; the
      project-pipeline definitions of each Project Template will be
      applied to this project.  If more than one template includes
      jobs for a given pipeline, they will be combined, as will any
      jobs specified in project-pipeline definitions on the project
      itself.

   .. attr:: default-branch
      :default: master

      The name of a branch that Zuul should check out in jobs if no
      better match is found.  Typically Zuul will check out the branch
      which matches the change under test, or if a job has specified
      an :attr:`job.override-checkout`, it will check that out.
      However, if there is no matching or override branch, then Zuul
      will checkout the default branch.

      Each project may only have one ``default-branch`` therefore Zuul
      will use the first value that it encounters for a given project
      (regardless of in which branch the definition appears).  It may
      not appear in a :ref:`project-template` definition.

   .. attr:: merge-mode
      :default: merge-resolve

      The merge mode which is used by Git for this project.  Be sure
      this matches what the remote system which performs merges (i.e.,
      Gerrit). The requested merge mode will be used by the Github driver
      when performing merges.

      Each project may only have one ``merge-mode`` therefore Zuul
      will use the first value that it encounters for a given project
      (regardless of in which branch the definition appears).  It may
      not appear in a :ref:`project-template` definition.

      It must be one of the following values:

      .. value:: merge

         Uses the default git merge strategy (recursive). This maps to
         the merge mode ``merge`` in Github.

      .. value:: merge-resolve

         Uses the resolve git merge strategy.  This is a very
         conservative merge strategy which most closely matches the
         behavior of Gerrit. This maps to the merge mode ``merge`` in
         Github.

      .. value:: cherry-pick

         Cherry-picks each change onto the branch rather than
         performing any merges. This is not supported by Github.

      .. value:: squash-merge

         Squash merges each change onto the branch. This maps to the
         merge mode ``squash`` in Github.

   .. attr:: vars
      :default: None

      A dictionary of variables to be made available for all jobs in
      all pipelines of this project.  For more information see
      :ref:`variable inheritance <user_jobs_variable_inheritance>`.

   .. attr:: <pipeline>

      Each pipeline that the project participates in should have an
      entry in the project.  The value for this key should be a
      dictionary with the following format:

      .. attr:: jobs
         :required:

         A list of jobs that should be run when items for this project
         are enqueued into the pipeline.  Each item of this list may
         be a string, in which case it is treated as a job name, or it
         may be a dictionary, in which case it is treated as a job
         variant local to this project and pipeline.  In that case,
         the format of the dictionary is the same as the top level
         :attr:`job` definition.  Any attributes set on the job here
         will override previous versions of the job.

      .. attr:: queue

         If this pipeline is a :value:`dependent
         <pipeline.manager.dependent>` pipeline, this specifies the
         name of the shared queue this project is in.  Any projects
         which interact with each other in tests should be part of the
         same shared queue in order to ensure that they don't merge
         changes which break the others.  This is a free-form string;
         just set the same value for each group of projects.

         Each pipeline for a project can only belong to one queue,
         therefore Zuul will use the first value that it encounters.
         It need not appear in the first instance of a :attr:`project`
         stanza; it may appear in secondary instances or even in a
         :ref:`project-template` definition.

         Pipeline managers other than `dependent` do not use this
         attribute, however, it may still be used if
         :attr:`scheduler.relative_priority` is enabled.

         .. note:: This attribute is not evaluated speculatively and
                   its setting shall be merged to be effective.

      .. attr:: debug

         If this is set to `true`, Zuul will include debugging
         information in reports it makes about items in the pipeline.
         This should not normally be set, but in situations were it is
         difficult to determine why Zuul did or did not run a certain
         job, the additional information this provides may help.

      .. attr:: fail-fast
         :default: false

         If this is set to `true`, Zuul will report a build failure
         immediately and abort all still running builds. This can be used
         to save resources in resource constrained environments at the cost
         of potentially requiring multiple attempts if more than one problem
         is present.

         Once this is defined it cannot be overridden afterwards. So this
         can be forced to a specific value by e.g. defining it in a config
         repo.

