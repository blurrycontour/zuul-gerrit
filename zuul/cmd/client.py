# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
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

import argparse
import babel.dates
import datetime
import json
import jwt
import logging
import prettytable
import os
import re
import sys
import time
import textwrap
import urllib.parse
from uuid import uuid4

import zuul.cmd
from zuul.lib.config import get_default
from zuul.model import SystemAttributes, PipelineState
from zuul.zk import ZooKeeperClient
from zuul.lib.keystorage import KeyStorage
from zuul.zk.locks import tenant_write_lock
from zuul.zk.zkobject import ZKContext
from zuul.zk.layout import LayoutState, LayoutStateStore
from zuul.zk.components import COMPONENT_REGISTRY


class Client(zuul.cmd.ZuulApp):
    app_name = 'zuul'
    app_description = 'Zuul CLI client.'
    log = logging.getLogger("zuul.Client")

    def createParser(self):
        parser = super(Client, self).createParser()
        parser.add_argument('-v', dest='verbose', action='store_true',
                            help='verbose output')

        subparsers = parser.add_subparsers(title='commands',
                                           description='valid commands',
                                           help='additional help')

        # Conf check
        cmd_conf_check = subparsers.add_parser(
            'tenant-conf-check',
            help='validate the tenant configuration')
        cmd_conf_check.set_defaults(func=self.validate)

        # Auth token
        cmd_create_auth_token = subparsers.add_parser(
            'create-auth-token',
            help='create an Authentication Token for the web API',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Create an Authentication Token for the administration web API

            Create a bearer token that can be used to access Zuul's
            administration web API. This is typically used to delegate
            privileged actions such as enqueueing and autoholding to
            third parties, scoped to a single tenant.
            At least one authenticator must be configured with a secret
            that can be used to sign the token.'''))
        cmd_create_auth_token.add_argument(
            '--auth-config',
            help=('The authenticator to use. '
                  'Must match an authenticator defined in zuul\'s '
                  'configuration file.'),
            default='zuul_operator',
            required=True)
        cmd_create_auth_token.add_argument(
            '--tenant',
            help='tenant name',
            required=True)
        cmd_create_auth_token.add_argument(
            '--user',
            help=("The user's name. Used for traceability in logs."),
            default=None,
            required=True)
        cmd_create_auth_token.add_argument(
            '--expires-in',
            help=('Token validity duration in seconds '
                  '(default: %i)' % 600),
            type=int,
            default=600,
            required=False)
        cmd_create_auth_token.set_defaults(func=self.create_auth_token)

        # Key storage
        cmd_import_keys = subparsers.add_parser(
            'import-keys',
            help='import project keys to ZooKeeper',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Import previously exported project secret keys to ZooKeeper

            Given a file with previously exported project keys, this
            command will import them into ZooKeeper.  Existing keys
            will not be overwritten; to overwrite keys, add the
            --force flag.'''))
        cmd_import_keys.set_defaults(command='import-keys')
        cmd_import_keys.add_argument('path', type=str,
                                     help='key export file path')
        cmd_import_keys.add_argument('--force', action='store_true',
                                     help='overwrite existing keys')
        cmd_import_keys.set_defaults(func=self.import_keys)

        cmd_export_keys = subparsers.add_parser(
            'export-keys',
            help='export project keys from ZooKeeper',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Export project secret keys from ZooKeeper

            This command exports project secret keys from ZooKeeper
            and writes them to a file which is suitable for backing
            up and later use with the import-keys command.

            The key contents are still protected by the keystore
            password and can not be used or decrypted without it.'''))
        cmd_export_keys.set_defaults(command='export-keys')
        cmd_export_keys.add_argument('path', type=str,
                                     help='key export file path')
        cmd_export_keys.set_defaults(func=self.export_keys)

        cmd_copy_keys = subparsers.add_parser(
            'copy-keys',
            help='copy keys from one project to another',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Copy secret keys from one project to another

            When projects are renamed, this command may be used to
            copy the secret keys from the current name to the new name
            in order to avoid service interruption.'''))
        cmd_copy_keys.set_defaults(command='copy-keys')
        cmd_copy_keys.add_argument('src_connection', type=str,
                                   help='original connection name')
        cmd_copy_keys.add_argument('src_project', type=str,
                                   help='original project name')
        cmd_copy_keys.add_argument('dest_connection', type=str,
                                   help='new connection name')
        cmd_copy_keys.add_argument('dest_project', type=str,
                                   help='new project name')
        cmd_copy_keys.set_defaults(func=self.copy_keys)

        cmd_delete_keys = subparsers.add_parser(
            'delete-keys',
            help='delete project keys',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Delete the ssh and secrets keys for a project
            '''))
        cmd_delete_keys.set_defaults(command='delete-keys')
        cmd_delete_keys.add_argument('connection', type=str,
                                     help='connection name')
        cmd_delete_keys.add_argument('project', type=str,
                                     help='project name')
        cmd_delete_keys.set_defaults(func=self.delete_keys)

        # ZK Maintenance
        cmd_delete_state = subparsers.add_parser(
            'delete-state',
            help='delete ephemeral ZooKeeper state',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Delete all ephemeral state stored in ZooKeeper

            Zuul stores a considerable amount of ephemeral state
            information in ZooKeeper.  Generally it should be able to
            detect and correct any errors, but if the state becomes
            corrupted and it is unable to recover, this command may be
            used to delete all ephemeral data from ZooKeeper and start
            anew.

            Do not run this command while any Zuul component is
            running (perform a complete shutdown first).

            This command will only remove ephemeral Zuul data from
            ZooKeeper; it will not remove private keys or Nodepool
            data.'''))
        cmd_delete_state.set_defaults(command='delete-state')
        cmd_delete_state.set_defaults(func=self.delete_state)

        cmd_delete_pipeline_state = subparsers.add_parser(
            'delete-pipeline-state',
            help='delete single pipeline ZooKeeper state',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Delete a single pipeline state stored in ZooKeeper

            In the unlikely event that a bug in Zuul or ZooKeeper data
            corruption occurs in such a way that it only affects a
            single pipeline, this command might be useful in
            attempting to recover.

            The circumstances under which this command will be able to
            effect a recovery are very rare and even so it may not be
            sufficient.  In general, if an error occurs it is better
            to shut Zuul down and run "zuul delete-state".

            This command will lock the specified tenant and
            then completely delete the pipeline state.'''))
        cmd_delete_pipeline_state.set_defaults(command='delete-pipeline-state')
        cmd_delete_pipeline_state.set_defaults(func=self.delete_pipeline_state)
        cmd_delete_pipeline_state.add_argument('tenant', type=str,
                                               help='tenant name')
        cmd_delete_pipeline_state.add_argument('pipeline', type=str,
                                               help='pipeline name')
        return parser

    def parseArguments(self, args=None):
        parser = super(Client, self).parseArguments()
        if not getattr(self.args, 'func', None):
            parser.print_help()
            sys.exit(1)

    def setup_logging(self):
        """Client logging does not rely on conf file"""
        if self.args.verbose:
            logging.basicConfig(level=logging.DEBUG)

    def main(self):
        self.parseArguments()
        self.readConfig()
        self.setup_logging()
        if self.args.func():
            sys.exit(0)
        else:
            sys.exit(1)

    def create_auth_token(self):
        auth_section = ''
        for section_name in self.config.sections():
            if re.match(r'^auth ([\'\"]?)%s(\1)$' % self.args.auth_config,
                        section_name, re.I):
                auth_section = section_name
                break
        if auth_section == '':
            print('"%s" authenticator configuration not found.'
                  % self.args.auth_config)
            sys.exit(1)
        now = time.time()
        token = {'iat': now,
                 'exp': now + self.args.expires_in,
                 'iss': get_default(self.config, auth_section, 'issuer_id'),
                 'aud': get_default(self.config, auth_section, 'client_id'),
                 'sub': self.args.user,
                 'zuul': {'admin': [self.args.tenant, ]},
                }
        driver = get_default(
            self.config, auth_section, 'driver')
        if driver == 'HS256':
            key = get_default(self.config, auth_section, 'secret')
        elif driver == 'RS256':
            private_key = get_default(self.config, auth_section, 'private_key')
            try:
                with open(private_key, 'r') as pk:
                    key = pk.read()
            except Exception as e:
                print('Could not read private key at "%s": %s' % (private_key,
                                                                  e))
                sys.exit(1)
        else:
            print('Unknown or unsupported authenticator driver "%s"' % driver)
            sys.exit(1)
        try:
            auth_token = jwt.encode(token,
                                    key=key,
                                    algorithm=driver)
            print("Bearer %s" % auth_token)
            err_code = 0
        except Exception as e:
            print("Error when generating Auth Token")
            print(e)
            err_code = 1
        finally:
            sys.exit(err_code)

    def validate(self):
        from zuul import scheduler
        from zuul import configloader
        self.configure_connections(source_only=True)

        class SchedulerConfig(scheduler.Scheduler):
            # A custom scheduler constructor adapted for config check
            # to avoid loading runtime clients.
            def __init__(self, config, connections):
                self.config = config
                self.connections = connections
                self.unparsed_config_cache = None

        zuul_globals = SystemAttributes.fromConfig(self.config)
        loader = configloader.ConfigLoader(
            self.connections, None, zuul_globals)
        sched = SchedulerConfig(self.config, self.connections)
        tenant_config, script = sched._checkTenantSourceConf(self.config)
        try:
            unparsed_abide = loader.readConfig(
                tenant_config, from_script=script)
            for conf_tenant in unparsed_abide.tenants.values():
                loader.tenant_parser.getSchema()(conf_tenant)
            print("Tenants config validated with success")
            err_code = 0
        except Exception as e:
            print("Error when validating tenants config")
            print(e)
            err_code = 1
        finally:
            sys.exit(err_code)

    def export_keys(self):
        logging.basicConfig(level=logging.INFO)

        zk_client = ZooKeeperClient.fromConfig(self.config)
        zk_client.connect()
        try:
            password = self.config["keystore"]["password"]
        except KeyError:
            raise RuntimeError("No key store password configured!")
        keystore = KeyStorage(zk_client, password=password)
        export = keystore.exportKeys()
        with open(os.open(self.args.path,
                          os.O_CREAT | os.O_WRONLY, 0o600), 'w') as f:
            json.dump(export, f)
        sys.exit(0)

    def import_keys(self):
        logging.basicConfig(level=logging.INFO)

        zk_client = ZooKeeperClient.fromConfig(self.config)
        zk_client.connect()
        try:
            password = self.config["keystore"]["password"]
        except KeyError:
            raise RuntimeError("No key store password configured!")
        keystore = KeyStorage(zk_client, password=password)
        with open(self.args.path, 'r') as f:
            import_data = json.load(f)
        keystore.importKeys(import_data, self.args.force)
        sys.exit(0)

    def copy_keys(self):
        logging.basicConfig(level=logging.INFO)

        zk_client = ZooKeeperClient.fromConfig(self.config)
        zk_client.connect()
        try:
            password = self.config["keystore"]["password"]
        except KeyError:
            raise RuntimeError("No key store password configured!")
        keystore = KeyStorage(zk_client, password=password)
        args = self.args
        # Load
        ssh = keystore.loadProjectSSHKeys(args.src_connection,
                                          args.src_project)
        secrets = keystore.loadProjectsSecretsKeys(args.src_connection,
                                                   args.src_project)
        # Save
        keystore.saveProjectSSHKeys(args.dest_connection,
                                    args.dest_project, ssh)
        keystore.saveProjectsSecretsKeys(args.dest_connection,
                                         args.dest_project, secrets)
        self.log.info("Copied keys from %s %s to %s %s",
                      args.src_connection, args.src_project,
                      args.dest_connection, args.dest_project)
        sys.exit(0)

    def delete_keys(self):
        logging.basicConfig(level=logging.INFO)

        zk_client = ZooKeeperClient.fromConfig(self.config)
        zk_client.connect()
        try:
            password = self.config["keystore"]["password"]
        except KeyError:
            raise RuntimeError("No key store password configured!")
        keystore = KeyStorage(zk_client, password=password)
        args = self.args
        keystore.deleteProjectSSHKeys(args.connection, args.project)
        keystore.deleteProjectsSecretsKeys(args.connection, args.project)
        keystore.deleteProjectDir(args.connection, args.project)
        self.log.info("Delete keys from %s %s",
                      args.connection, args.project)
        sys.exit(0)

    def delete_state(self):
        logging.basicConfig(level=logging.INFO)

        zk_client = ZooKeeperClient.fromConfig(self.config)
        zk_client.connect()
        confirm = input("Are you sure you want to delete "
                        "all ephemeral data from ZooKeeper? (yes/no) ")
        if confirm.strip().lower() == 'yes':
            zk_client.client.delete('/zuul', recursive=True)
        sys.exit(0)

    def delete_pipeline_state(self):
        logging.basicConfig(level=logging.INFO)

        zk_client = ZooKeeperClient.fromConfig(self.config)
        zk_client.connect()

        args = self.args
        safe_tenant = urllib.parse.quote_plus(args.tenant)
        safe_pipeline = urllib.parse.quote_plus(args.pipeline)
        COMPONENT_REGISTRY.create(zk_client)
        with tenant_write_lock(zk_client, args.tenant) as lock:
            path = f'/zuul/tenant/{safe_tenant}/pipeline/{safe_pipeline}'
            layout_uuid = None
            zk_client.client.delete(
                f'/zuul/tenant/{safe_tenant}/pipeline/{safe_pipeline}',
                recursive=True)
            context = ZKContext(zk_client, lock, None, self.log)
            ps = PipelineState.new(context, _path=path,
                                   layout_uuid=layout_uuid)
            # Force everyone to make a new layout for this tenant in
            # order to rebuild the shared change queues.
            layout_state = LayoutState(
                tenant_name=args.tenant,
                hostname='admin command',
                last_reconfigured=int(time.time()),
                uuid=uuid4().hex,
                branch_cache_min_ltimes={},
                ltime=ps._zstat.last_modified_transaction_id,
            )
            tenant_layout_state = LayoutStateStore(zk_client, lambda: None)
            tenant_layout_state[args.tenant] = layout_state

        sys.exit(0)


def main():
    Client().main()
