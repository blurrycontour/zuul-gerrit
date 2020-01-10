Secret Definition
=================

.. attr:: secret

   The following attributes must appear on a secret:

   .. attr:: name
      :required:

      The name of the secret, used in a :ref:`job` definition to
      request the secret.

   .. attr:: data
      :required:

      A dictionary which will be added to the Ansible variables
      available to the job.  The values can be any of the normal YAML
      data types (strings, integers, dictionaries or lists) or
      encrypted strings.  See :ref:`encryption` for more information.

