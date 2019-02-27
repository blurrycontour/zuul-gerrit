# Copyright 2019 OpenStack Foundation
# Copyright 2019 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import logging
import os.path
import re
import jwt

from zuul import exceptions
from zuul.lib.yamlutil import safe_load as yaml_safe_load
import zuul.driver.auth.jwt as auth_jwt
from zuul.configloader import AuthorizationRuleParser


"""AuthN/AuthZ related library, used by zuul-web."""


class AuthorizationRegistry(object):
    """Registry of authorization rules"""

    log = logging.getLogger("Zuul.AuthorizationRegistry")

    def __init__(self):
        self.ruleset = {}

    # TODO a lot of this and expandConfigPath duplicate code in configloader.py
    def reconfigure(self, config):
        # TODO should the [web] section be mandatory?
        if 'web' not in config.sections():
            return
        web_config = dict(config.items('web'))
        config_path = web_config.get('authorizations_config', None)
        if config_path is None:
            # no rules to parse
            return
        cpath = self.expandConfigPath(config_path)
        with open(cpath) as f:
            rules = yaml_safe_load(f)
        if not isinstance(rules, list):
            raise Exception('Authorizations file must be a list of rules')
        new_ruleset = {}
        ruleparser = AuthorizationRuleParser()
        for rule in rules:
            if not isinstance(rule, dict):
                raise Exception('Invalid rule format for rule "%r"' % rule)
            if len(rule.keys()) > 1:
                raise Exception('Rules must consist of "rule" element only')
            if 'rule' in rule:
                rule_tree = ruleparser.fromYaml(rule['rule'])
                if rule_tree.name in new_ruleset:
                    raise Exception(
                        'Rule "%s" is defined at least twice' % rule_tree.name)
                else:
                    new_ruleset[rule_tree.name] = rule_tree
            else:
                raise Exception('Unknown element "%s"' % rule.keys()[0])
        self.ruleset = new_ruleset

    def expandConfigPath(self, config_path):
        if config_path:
            config_path = os.path.expanduser(config_path)
        if not os.path.exists(config_path):
            raise Exception("Unable to read authorization config file at %s" %
                            config_path)
        return config_path


class AuthenticatorRegistry(object):
    """Registry of authenticators as they are declared in the configuration"""

    log = logging.getLogger("Zuul.AuthenticatorRegistry")

    def __init__(self):
        self.authenticators = {}

    def configure(self, config):
        for section_name in config.sections():
            auth_match = re.match(r'^auth ([\'\"]?)(.*)(\1)$',
                                  section_name, re.I)
            if not auth_match:
                continue
            auth_name = auth_match.group(2)
            auth_config = dict(config.items(section_name))

            if 'driver' not in auth_config:
                raise Exception("Auth driver needed for %s" % auth_name)

            auth_driver = auth_config['driver']
            try:
                driver = auth_jwt.get_authenticator_by_name(auth_driver)
            except IndexError:
                raise Exception(
                    "Unknown driver %s for auth %s" % (auth_driver,
                                                       auth_name))
            # TODO catch config specific errors (missing fields)
            self.authenticators[auth_name] = driver(**auth_config)

    def authenticate(self, rawToken):
        unverified = jwt.decode(rawToken, verify=False)
        realm = ''
        for auth_name in self.authenticators:
            authenticator = self.authenticators[auth_name]
            realm = authenticator.realm
            if authenticator.issuer_id == unverified.get('iss', ''):
                return authenticator.authenticate(rawToken)
        # No known issuer found, arbitrarily set realm to first configured
        raise exceptions.IssuerUnknownError(realm)
