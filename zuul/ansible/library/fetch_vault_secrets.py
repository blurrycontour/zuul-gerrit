#!/usr/bin/python

# Copyright: (c) 2018, Terry Jones <terry.jones@example.org>
# GNU General Public License v3.0+
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: fetch_vault_secrets

short_description: fetch Vault secrets from a Zuul secret

version_added: "2.5"

description:
    - "This module reads a Zuul secret and find secrets which has to be read in
    Vault. If a secret value starts with VAULT::, the module will try to read
    the value in Vault from given path"

options:
    secret_name:
        description:
            - The name under which the secret will be registered in hostvars
    zuul_secret:
        description:
            - This is the Zuul secret to read
        required: true
    vault_approle_credentials:
        description:
            - This is the Zuul secret containing the role_id and the secret_id
        required: true

author:
    - Benoit Bayszczak
'''

EXAMPLES = '''
# Dummy declaration of Zuul secret containing approle IDs
  - name: set Vault IDs
    set_fact:
      vault_approle_credentials:
        url: https://HOST:PORT
        mount_point: APPROLE_MOUNT_POINT
        role_id: ROLE_ID
        secret_id: SECRET_ID

# Dummy declaration of a Zuul secret
- name: set secret
    set_fact:
      my_zuul_secret:
        test_value_1: "VAULT::apps/app_1/test:k"
        test_value_2: "VAULT::apps/app_1/test:k"
        dummy_secret: "value"
        dummy_secret2: "value"

# Replace variables in Zuul secret then override previous Zuul secret value
 - name: test new module
    fetch_vault_secrets:
      secret_name: my_awesome_secret
      zuul_secret: "{{ my_zuul_secret }}"
      vault_approle_credentials: "{{ vault_approle_credentials }}"

# Dump secret
  - name: dump secret
    debug:
      msg: '{{ my_awesome_secret }}'
'''

RETURN = '''
secret_name:
    description: A copy of original Zuul secret with Vault secrets overwritten
    type: dict
'''

import hvac


from ansible.module_utils.basic import AnsibleModule


def run_module():
    module_args = dict(
        secret_name=dict(type='str', required=True),
        zuul_secret=dict(type='dict', required=True),
        vault_approle_credentials=dict(type='dict', required=True)
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # We create a working copy for the Zuul secret
    working_secret = module.params['zuul_secret']
    # We fetch the secret name
    secret_name = module.params['secret_name']

    # Check to see if Vault auth creds are properly received and formatted
    needed = ['url', 'mount_point', 'role_id', 'secret_id']
    have = module.params['vault_approle_credentials'].keys()
    if not all(param in have for param in needed):
        module.exit_json(
            changed=False, failed=True,
            error="vault_approle_credentials not properly formatted"
        )

    # Saving Vault data to vars
    vault_role_id = module.params['vault_approle_credentials']['role_id']
    vault_secret_id = module.params['vault_approle_credentials']['secret_id']
    vault_approle_mount_point = \
        module.params['vault_approle_credentials']['mount_point']
    vault_url = module.params['vault_approle_credentials']['url']

    # If check mode, exit without display secrets
    if module.check_mode:
        module.exit_json(
            changed=False, failed=False,
            ansible_facts={secret_name: {}}
        )

    try:
        hvac_client = hvac.Client(url=vault_url)
            # Fetch token using approle
        hvac_client.auth_approle(
            role_id=vault_role_id,
            secret_id=vault_secret_id,
            mount_point=vault_approle_mount_point
        )
        for secret in working_secret:
            # For all secrets in Zuul secret where value starts with 'VAULT::'
            if working_secret[secret].startswith("VAULT::"):

                # With working_secret[secret] == "VAULT::mp/path/to:k"
                secret_access_path = working_secret[secret][7:]
                # secret_access_path == "mp/path/to:k"
                secret_mount_point = secret_access_path.split('/')[0]
                # secret_mount_point = "mp"
                splitted_path = secret_access_path.split(':')
                secret_path = splitted_path[0][len(secret_mount_point) + 1:]
                # secret_path == path/to
                secret_key = splitted_path[1]
                # secret_key == "k"

                read_secret = hvac_client.secrets.kv.v1.read_secret(
                    mount_point=secret_mount_point,
                    path=secret_path
                )["data"]

                # If key not in secret, exit
                if secret_key not in read_secret:
                    module.exit_json(
                        changed=False,
                        failed=True,
                        error=("%s:%s does not exists" %
                               (secret_path, secret_key))
                    )
                # Replace VAULT::path/key with found value
                working_secret[secret] = read_secret[secret_key]
    except Exception as e:
        # Need to add 'invocation' to avoid potential secret display
        module.exit_json(
            changed=False, failed=True,
            error=str(e), invocation=""
        )

    module.exit_json(
        changed=True, failed=False,
        ansible_facts={secret_name: working_secret}
    )


def main():
    run_module()


if __name__ == '__main__':
    main()
