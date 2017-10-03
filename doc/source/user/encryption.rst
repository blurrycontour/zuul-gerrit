:title: Encryption

.. _encryption:

Encryption
==========

Zuul supports storing encrypted data directly in the git repositories
of projects it operates on.  If you have a job which requires private
information in order to run (e.g., credentials to interact with a
third-party service) those credentials can be stored along with the
job definition.

Each project in Zuul has its own automatically generated RSA keypair
which can be used by anyone to encrypt a secret and only Zuul is able
to decrypt it.  Zuul serves each project's public key using its
build-in webserver.  They can be fetched at the path
``/keys/<source>/<project>.pub`` where ``<project>`` is the name of a
project and ``<source>`` is the name of that project's connection in
the main Zuul configuration file.

Zuul currently supports one encryption scheme, PKCS#1 with OAEP, which
can not store secrets longer than the 3760 bits (derived from the key
length of 4096 bits minus 336 bits of overhead).  The padding used by
this scheme ensures that someone examining the encrypted data can not
determine the length of the plaintext version of the data, except to
know that it is not longer than 3760 bits (or some multiple thereof).

In the config files themselves, Zuul uses an extensible method of
specifying the encryption scheme used for a secret so that other
schemes may be added later.  To specify a secret, use the
``!encrypted/pkcs1-oaep`` YAML tag along with the base64 encoded
value.  For example:

.. code-block:: yaml

  - secret:
      name: test_secret
      data:
        password: !encrypted/pkcs1-oaep |
          BFhtdnm8uXx7kn79RFL/zJywmzLkT1GY78P3bOtp4WghUFWobkifSu7ZpaV4NeO0s71YUsi
          ...

To support secrets longer than 3760 bits, the value after the
encryption tag may be a list rather than a scalar.  For example:

.. code-block:: yaml

  - secret:
      name: long_secret
      data:
        password: !encrypted/pkcs1-oaep
          - er1UXNOD3OqtsRJaP0Wvaqiqx0ZY2zzRt6V9vqIsRaz1R5C4/AEtIad/DERZHwk3Nk+KV
            ...
          - HdWDS9lCBaBJnhMsm/O9tpzCq+GKRELpRzUwVgU5k822uBwhZemeSrUOLQ8hQ7q/vVHln
            ...

Using the secrets can only be done in whitelisted pipelines. Most commonly this
will be in a job running the post pipeline.

The secret must be defined in the job description. There are two ways to define
the secret. The first uses the secret name as the variable name. The second
maps the secret to a different variable name. For example:

.. code-block:: yaml

  - job:
      name: publish-my-project
      secrets:
        - long_secret
        - secret: test_secret
          name: myapp

After defining the secret you can use it as you would any other variable. You
must be careful not to expose the secret via the ansible logs since the logs
are publically available. The ``no_log: True`` paramater for Ansible can help
with that. Of note, the secret name should be globally unique, so including
your project name is recommended. Using the secrets above to continue the
example:

.. code-block:: yaml

  - hosts: all
    tasks:
      - name: Log into application
        command: myapp -p {{ myapp.password }}
        no_log: True

      - name: Write password to file
        copy:
          content: "{{ long_secret.password }}"
          dest: /etc/myapp/password_file
        no_log: True

Zuul provides a standalone script to make encrypting values easy; it
can be found at `tools/encrypt_secret.py` in the Zuul source
directory.

.. program-output:: python3 ../../tools/encrypt_secret.py --help

