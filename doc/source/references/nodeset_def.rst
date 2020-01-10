Nodeset Definition
==================

.. attr:: nodeset

   A Nodeset requires two attributes:

   .. attr:: name
      :required:

      The name of the Nodeset, to be referenced by a :ref:`job`.

   .. attr:: nodes
      :required:

      A list of node definitions, each of which has the following format:

      .. attr:: name
         :required:

         The name of the node.  This will appear in the Ansible inventory
         for the job.

         This can also be as a list of strings. If so, then the list of hosts in
         the Ansible inventory will share a common ansible_host address.

      .. attr:: label
         :required:

         The Nodepool label for the node.  Zuul will request a node with
         this label.

   .. attr:: groups

      Additional groups can be defined which are accessible from the ansible
      playbooks.

      .. attr:: name
         :required:

         The name of the group to be referenced by an ansible playbook.

      .. attr:: nodes
         :required:

         The nodes that shall be part of the group. This is specified as a list
         of strings.

