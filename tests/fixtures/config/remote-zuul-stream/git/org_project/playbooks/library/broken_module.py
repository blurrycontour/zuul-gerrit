#!/usr/bin/env python

def main():
    print("This module is broken")

try:
    from ansible.module_utils.basic import *  # noqa
    from ansible.module_utils.basic import AnsibleModule
except ImportError:
    pass

if __name__ == '__main__':
    main()
