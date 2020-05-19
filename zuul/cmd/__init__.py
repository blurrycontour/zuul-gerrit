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

import abc
import argparse
import configparser
import daemon
import extras
import io
import logging
import logging.config
import os
import prettytable
import signal
import socket
import sys
import textwrap
import traceback
import threading
import time

yappi = extras.try_import('yappi')
objgraph = extras.try_import('objgraph')

# as of python-daemon 1.6 it doesn't bundle pidlockfile anymore
# instead it depends on lockfile-0.9.1 which uses pidfile.
pid_file_module = extras.try_imports(['daemon.pidlockfile', 'daemon.pidfile'])

from zuul.ansible import logconfig
import zuul.lib.connections
from zuul.lib.config import get_default


def stack_dump_handler(signum, frame):
    signal.signal(signal.SIGUSR2, signal.SIG_IGN)
    log = logging.getLogger("zuul.stack_dump")
    log.debug("Beginning debug handler")
    try:
        threads = {}
        for t in threading.enumerate():
            threads[t.ident] = t
        log_str = ""
        for thread_id, stack_frame in sys._current_frames().items():
            thread = threads.get(thread_id)
            if thread:
                thread_name = thread.name
                thread_is_daemon = str(thread.daemon)
            else:
                thread_name = '(Unknown)'
                thread_is_daemon = '(Unknown)'
            log_str += "Thread: %s %s d: %s\n"\
                       % (thread_id, thread_name, thread_is_daemon)
            log_str += "".join(traceback.format_stack(stack_frame))
        log.debug(log_str)
    except Exception:
        log.exception("Thread dump error:")
    try:
        if yappi:
            if not yappi.is_running():
                log.debug("Starting Yappi")
                yappi.start()
            else:
                log.debug("Stopping Yappi")
                yappi.stop()
                yappi_out = io.StringIO()
                yappi.get_func_stats().print_all(out=yappi_out)
                yappi.get_thread_stats().print_all(out=yappi_out)
                log.debug(yappi_out.getvalue())
                yappi_out.close()
                yappi.clear_stats()
    except Exception:
        log.exception("Yappi error:")
    try:
        if objgraph:
            log.debug("Most common types:")
            objgraph_out = io.StringIO()
            objgraph.show_growth(limit=100, file=objgraph_out)
            log.debug(objgraph_out.getvalue())
            objgraph_out.close()
    except Exception:
        log.exception("Objgraph error:")
    log.debug("End debug handler")
    signal.signal(signal.SIGUSR2, stack_dump_handler)


class ZuulApp(object):
    app_name = None  # type: str
    app_description = None  # type: str

    def __init__(self):
        self.args = None
        self.config = None
        self.connections = {}

    def _get_version(self):
        from zuul.version import version_info as zuul_version_info
        return "Zuul version: %s" % zuul_version_info.release_string()

    def createParser(self):
        parser = argparse.ArgumentParser(
            description=self.app_description,
            formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('-c', dest='config',
                            help='specify the config file')
        parser.add_argument('--version', dest='version', action='version',
                            version=self._get_version(),
                            help='show zuul version')
        return parser

    def parseArguments(self, args=None):
        parser = self.createParser()
        self.args = parser.parse_args(args)

        # The arguments debug and foreground both lead to nodaemon mode so
        # set nodaemon if one of them is set.
        if ((hasattr(self.args, 'debug') and self.args.debug) or
                (hasattr(self.args, 'foreground') and self.args.foreground)):
            self.args.nodaemon = True
        else:
            self.args.nodaemon = False
        return parser

    def readConfig(self):
        safe_env = {
            k: v for k, v in os.environ.items()
            if k.startswith('ZUUL_')
        }
        self.config = configparser.ConfigParser(safe_env)
        if self.args.config:
            locations = [self.args.config]
        else:
            locations = ['/etc/zuul/zuul.conf',
                         '~/zuul.conf']
        for fp in locations:
            if os.path.exists(os.path.expanduser(fp)):
                self.config.read(os.path.expanduser(fp))
                return
        raise Exception("Unable to locate config file in %s" % locations)

    def setup_logging(self, section, parameter):
        if self.config.has_option(section, parameter):
            fp = os.path.expanduser(self.config.get(section, parameter))
            logging_config = logconfig.load_config(fp)
        else:
            # If someone runs in the foreground and doesn't give a logging
            # config, leave the config set to emit to stdout.
            if hasattr(self.args, 'nodaemon') and self.args.nodaemon:
                logging_config = logconfig.ServerLoggingConfig()
            else:
                # Setting a server value updates the defaults to use
                # WatchedFileHandler on /var/log/zuul/{server}-debug.log
                # and /var/log/zuul/{server}.log
                logging_config = logconfig.ServerLoggingConfig(server=section)
            if hasattr(self.args, 'debug') and self.args.debug:
                logging_config.setDebug()
        logging_config.apply()

    def configure_connections(self, source_only=False, include_drivers=None):
        self.connections = zuul.lib.connections.ConnectionRegistry()
        self.connections.configure(self.config, source_only, include_drivers)


class ZuulDaemonApp(ZuulApp, metaclass=abc.ABCMeta):
    def createParser(self):
        parser = super(ZuulDaemonApp, self).createParser()
        parser.add_argument('-d', dest='debug', action='store_true',
                            help='run in foreground with debug log. Note '
                                 'that in future this will be changed to only '
                                 'request debug logging. If you want to keep '
                                 'running the process in the foreground '
                                 'migrate/add the -f switch.')
        parser.add_argument('-f', dest='foreground', action='store_true',
                            help='run in foreground with info log')
        return parser

    def getPidFile(self):
        pid_fn = get_default(self.config, self.app_name, 'pidfile',
                             '/var/run/zuul/%s.pid' % self.app_name,
                             expand_user=True)
        return pid_fn

    @abc.abstractmethod
    def run(self):
        """
        This is the main run method of the application.
        """
        pass

    def setup_logging(self, section, parameter):
        super(ZuulDaemonApp, self).setup_logging(section, parameter)
        from zuul.version import version_info as zuul_version_info
        log = logging.getLogger(
            "zuul.{section}".format(section=section.title()))
        log.debug(
            "Configured logging: {version}".format(
                version=zuul_version_info.release_string()))

    def main(self):
        self.parseArguments()
        self.readConfig()

        pid_fn = self.getPidFile()
        pid = pid_file_module.TimeoutPIDLockFile(pid_fn, 10)

        # Early register the stack dump handler for all zuul apps. This makes
        # it possible to also gather stack dumps during startup hangs.
        signal.signal(signal.SIGUSR2, stack_dump_handler)

        if self.args.nodaemon:
            self.run()
        else:
            # Exercise the pidfile before we do anything else (including
            # logging or daemonizing)
            with pid:
                pass

            with daemon.DaemonContext(pidfile=pid, umask=0o022):
                self.run()

    def send_command(self, cmd):
        command_socket = get_default(
            self.config, self.app_name, 'command_socket',
            '/var/lib/zuul/%s.socket' % self.app_name)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(command_socket)
        cmd = '%s\n' % cmd
        s.sendall(cmd.encode('utf8'))


class ZuulClientApp(ZuulApp):

    def createParser(self):
        parser = super(ZuulClientApp, self).createParser()
        parser.add_argument('-v', dest='verbose', action='store_true',
                            help='verbose output')
        self.createCommandParsers(parser)
        return parser

    def createCommandParsers(self, parser):
        subparsers = parser.add_subparsers(title='commands',
                                           description='valid commands',
                                           help='additional help')
        # Add parsers that are common to RPC and REST clients
        self.add_autohold_subparser(subparsers)
        self.add_autohold_delete_subparser(subparsers)
        self.add_autohold_info_subparser(subparsers)
        self.add_autohold_list_subparser(subparsers)
        self.add_enqueue_subparser(subparsers)
        self.add_enqueue_ref_subparser(subparsers)
        self.add_dequeue_subparser(subparsers)
        self.add_promote_subparser(subparsers)

        return subparsers

    def parseArguments(self, args=None):
        parser = super(ZuulClientApp, self).parseArguments()
        if not getattr(self.args, 'func', None):
            parser.print_help()
            sys.exit(1)
        if self.args.func == self.enqueue_ref:
            # if oldrev or newrev is set, ensure they're not the same
            if (self.args.oldrev is not None) or \
               (self.args.newrev is not None):
                if self.args.oldrev == self.args.newrev:
                    parser.error(
                        "The old and new revisions must not be the same.")
            # if they're not set, we pad them out to zero
            if self.args.oldrev is None:
                self.args.oldrev = '0000000000000000000000000000000000000000'
            if self.args.newrev is None:
                self.args.newrev = '0000000000000000000000000000000000000000'
        if self.args.func == self.dequeue:
            if self.args.change is None and self.args.ref is None:
                parser.error("Change or ref needed.")
            if self.args.change is not None and self.args.ref is not None:
                parser.error(
                    "The 'change' and 'ref' arguments are mutually exclusive.")

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

    def get_client(self):
        raise NotImplementedError('No client defined')

    def add_autohold_subparser(self, subparsers):
        cmd_autohold = subparsers.add_parser(
            'autohold', help='hold nodes for failed job')
        cmd_autohold.add_argument('--tenant', help='tenant name',
                                  required=True)
        cmd_autohold.add_argument('--project', help='project name',
                                  required=True)
        cmd_autohold.add_argument('--job', help='job name',
                                  required=True)
        cmd_autohold.add_argument('--change',
                                  help='specific change to hold nodes for',
                                  required=False, default='')
        cmd_autohold.add_argument('--ref', help='git ref to hold nodes for',
                                  required=False, default='')
        cmd_autohold.add_argument('--reason', help='reason for the hold',
                                  required=True)
        cmd_autohold.add_argument('--count',
                                  help='number of job runs (default: 1)',
                                  required=False, type=int, default=1)
        cmd_autohold.add_argument(
            '--node-hold-expiration',
            help=('how long in seconds should the node set be in HOLD status '
                  '(default: scheduler\'s default_hold_expiration value)'),
            required=False, type=int)
        cmd_autohold.set_defaults(func=self.autohold)

    def autohold(self):
        if self.args.change and self.args.ref:
            print("Change and ref can't be both used for the same request")
            return False
        if "," in self.args.change:
            print("Error: change argument can not contain any ','")
            return False

        node_hold_expiration = self.args.node_hold_expiration
        client = self.get_client()
        r = client.autohold(
            tenant=self.args.tenant,
            project=self.args.project,
            job=self.args.job,
            change=self.args.change,
            ref=self.args.ref,
            reason=self.args.reason,
            count=self.args.count,
            node_hold_expiration=node_hold_expiration)
        return r

    def add_autohold_delete_subparser(self, subparsers):
        cmd_autohold_delete = subparsers.add_parser(
            'autohold-delete', help='delete autohold request')
        cmd_autohold_delete.set_defaults(func=self.autohold_delete)
        cmd_autohold_delete.add_argument('--tenant', help='tenant name',
                                         required=False, default=None)
        cmd_autohold_delete.add_argument('id', metavar='REQUEST_ID',
                                         help='the hold request ID')

    def autohold_delete(self):
        client = self.get_client()
        return client.autohold_delete(self.args.id)

    def add_autohold_info_subparser(self, subparsers):
        cmd_autohold_info = subparsers.add_parser(
            'autohold-info', help='retrieve autohold request detailed info')
        cmd_autohold_info.set_defaults(func=self.autohold_info)
        cmd_autohold_info.add_argument('--tenant', help='tenant name',
                                       required=False, default=None)
        cmd_autohold_info.add_argument('id', metavar='REQUEST_ID',
                                       help='the hold request ID')

    def autohold_info(self):
        client = self.get_client()
        request = client.autohold_info(self.args.id)

        if not request:
            print("Autohold request not found")
            return True

        print("ID: %s" % request['id'])
        print("Tenant: %s" % request['tenant'])
        print("Project: %s" % request['project'])
        print("Job: %s" % request['job'])
        print("Ref Filter: %s" % request['ref_filter'])
        print("Max Count: %s" % request['max_count'])
        print("Current Count: %s" % request['current_count'])
        print("Node Expiration: %s" % request['node_expiration'])
        print("Request Expiration: %s" % time.ctime(request['expired']))
        print("Reason: %s" % request['reason'])
        print("Held Nodes: %s" % request['nodes'])

        return True

    def add_autohold_list_subparser(self, subparsers):
        cmd_autohold_list = subparsers.add_parser(
            'autohold-list', help='list autohold requests')
        cmd_autohold_list.add_argument('--tenant', help='tenant name',
                                       required=True)
        cmd_autohold_list.set_defaults(func=self.autohold_list)

    def autohold_list(self):
        client = self.get_client()
        autohold_requests = client.autohold_list(tenant=self.args.tenant)

        if not autohold_requests:
            print("No autohold requests found")
            return True

        table = prettytable.PrettyTable(
            field_names=[
                'ID', 'Tenant', 'Project', 'Job', 'Ref Filter',
                'Max Count', 'Reason'
            ])

        for request in autohold_requests:
            table.add_row([
                request['id'],
                request['tenant'],
                request['project'],
                request['job'],
                request['ref_filter'],
                request['max_count'],
                request['reason'],
            ])

        print(table)
        return True

    def add_enqueue_subparser(self, subparsers):
        cmd_enqueue = subparsers.add_parser('enqueue', help='enqueue a change')
        cmd_enqueue.add_argument('--tenant', help='tenant name',
                                 required=True)
        cmd_enqueue.add_argument('--trigger',
                                 help='trigger name (deprecated and ignored. '
                                      'Kept only for backward compatibility)',
                                 required=False, default=None)
        cmd_enqueue.add_argument('--pipeline', help='pipeline name',
                                 required=True)
        cmd_enqueue.add_argument('--project', help='project name',
                                 required=True)
        cmd_enqueue.add_argument('--change', help='change id',
                                 required=True)
        cmd_enqueue.set_defaults(func=self.enqueue)

    def enqueue(self):
        client = self.get_client()
        r = client.enqueue(
            tenant=self.args.tenant,
            pipeline=self.args.pipeline,
            project=self.args.project,
            trigger=self.args.trigger,
            change=self.args.change)
        return r

    def add_enqueue_ref_subparser(self, subparsers):
        cmd_enqueue = subparsers.add_parser(
            'enqueue-ref', help='enqueue a ref',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Submit a trigger event

            Directly enqueue a trigger event.  This is usually used
            to manually "replay" a trigger received from an external
            source such as gerrit.'''))
        cmd_enqueue.add_argument('--tenant', help='tenant name',
                                 required=True)
        cmd_enqueue.add_argument('--trigger', help='trigger name',
                                 required=False, default=None)
        cmd_enqueue.add_argument('--pipeline', help='pipeline name',
                                 required=True)
        cmd_enqueue.add_argument('--project', help='project name',
                                 required=True)
        cmd_enqueue.add_argument('--ref', help='ref name',
                                 required=True)
        cmd_enqueue.add_argument(
            '--oldrev', help='old revision', default=None)
        cmd_enqueue.add_argument(
            '--newrev', help='new revision', default=None)
        cmd_enqueue.set_defaults(func=self.enqueue_ref)

    def enqueue_ref(self):
        client = self.get_client()
        r = client.enqueue_ref(
            tenant=self.args.tenant,
            pipeline=self.args.pipeline,
            project=self.args.project,
            trigger=self.args.trigger,
            ref=self.args.ref,
            oldrev=self.args.oldrev,
            newrev=self.args.newrev)
        return r

    def add_dequeue_subparser(self, subparsers):
        cmd_dequeue = subparsers.add_parser('dequeue',
                                            help='dequeue a buildset by its '
                                                 'change or ref')
        cmd_dequeue.add_argument('--tenant', help='tenant name',
                                 required=True)
        cmd_dequeue.add_argument('--pipeline', help='pipeline name',
                                 required=True)
        cmd_dequeue.add_argument('--project', help='project name',
                                 required=True)
        cmd_dequeue.add_argument('--change', help='change id',
                                 default=None)
        cmd_dequeue.add_argument('--ref', help='ref name',
                                 default=None)
        cmd_dequeue.set_defaults(func=self.dequeue)

    def dequeue(self):
        client = self.get_client()
        r = client.dequeue(
            tenant=self.args.tenant,
            pipeline=self.args.pipeline,
            project=self.args.project,
            change=self.args.change,
            ref=self.args.ref)
        return r

    def add_promote_subparser(self, subparsers):
        cmd_promote = subparsers.add_parser('promote',
                                            help='promote one or more changes')
        cmd_promote.add_argument('--tenant', help='tenant name',
                                 required=True)
        cmd_promote.add_argument('--pipeline', help='pipeline name',
                                 required=True)
        cmd_promote.add_argument('--changes', help='change ids',
                                 required=True, nargs='+')
        cmd_promote.set_defaults(func=self.promote)

    def promote(self):
        client = self.get_client()
        r = client.promote(
            tenant=self.args.tenant,
            pipeline=self.args.pipeline,
            change_ids=self.args.changes)
        return r
