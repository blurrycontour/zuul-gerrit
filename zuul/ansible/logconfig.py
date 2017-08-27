# Copyright 2017 Red Hat, Inc.
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
import logging.config
import json
import os

import yaml

_DEFAULT_JOB_LOGGING_CONFIG = {
    'version': 1,
    'formatters': {
        'plain': {'format': '%(message)s'},
        'result': {'format': 'RESULT %(message)s'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'level': 'INFO',
            'formatter': 'plain',
        },
        'result': {
            # result is returned to subprocess stdout and is used to pass
            # control information from the callback back to the executor
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'level': 'INFO',
            'formatter': 'result',
        },
        'jobfile': {
            # used by executor to emit log file
            'class': 'logging.FileHandler',
            'level': 'INFO',
            'formatter': 'plain',
        },
    },
    'loggers': {
        'zuul.executor.ansible.result': {
            'handlers': ['result'],
            'level': 'INFO',
        },
        'zuul.executor.ansible': {
            'handlers': ['jobfile'],
            'level': 'INFO',
        },
        'sqlalchemy.engine': {
            'handlers': ['console'],
            'level': 'WARN',
        },
        'alembic': {
            'handlers': ['console'],
            'level': 'WARN',
        },
    },
    'root': {'handlers': []},
}

_DEFAULT_SERVER_LOGGING_CONFIG = {
    'version': 1,
    'formatters': {
        'simple': {
            'format': '%(asctime)s %(levelname)s %(name)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            # Used for printing to stdout
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'level': 'WARNING',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'zuul': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
        'sqlalchemy.engine': {
            'handlers': ['console'],
            'level': 'WARN',
        },
        'gerrit': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'gear': {
            'handlers': ['console'],
            'level': 'WARN',
        },
        'alembic': {
            'handlers': ['console'],
            'level': 'WARN',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARN',
    },
}

_DEFAULT_SERVER_FILE_HANDLERS = {
    'normal': {
        # Used for writing normal log files
        'class': 'logging.handlers.WatchedFileHandler',
        # This will get set to something real by DictLoggingConfig.server
        'filename': '/var/log/zuul/{server}.log',
        'level': 'INFO',
        'formatter': 'simple',
    },
    'debug': {
        # Used for writing debug log files
        'class': 'logging.handlers.WatchedFileHandler',
        # This will get set to something real by DictLoggingConfig.server
        'filename': '/var/log/zuul/{server}-debug.log',
        'level': 'DEBUG',
        'formatter': 'simple',
    },
}


def _read_config_file(filename: str):
    if not os.path.exists(filename):
        raise ValueError("Unable to read logging config file at %s" % filename)

    if os.path.splitext(filename)[1] in ('.yml', '.yaml', '.json'):
        return yaml.safe_load(open(filename, 'r'))
    return filename


def load_config(filename: str):
    config = _read_config_file(filename)
    if isinstance(config, dict):
        return DictLoggingConfig(config)
    return FileLoggingConfig(filename)


def load_job_config(filename: str):
    return JobLoggingConfig(_read_config_file(filename))


class LoggingConfig(object, metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def apply(self):
        """Apply the config information to the current logging config."""


class DictLoggingConfig(LoggingConfig, metaclass=abc.ABCMeta):

    def __init__(self, config):
        self._config = config

    def apply(self):
        logging.config.dictConfig(self._config)

    def writeJson(self, filename: str):
        open(filename, 'w').write(json.dumps(self._config, indent=2))


class JobLoggingConfig(DictLoggingConfig):

    def __init__(self, config=None, job_output_file=None):
        if not config:
            config = _DEFAULT_JOB_LOGGING_CONFIG.copy()
        super(JobLoggingConfig, self).__init__(config=config)
        if job_output_file:
            self.job_output_file = job_output_file

    def setDebug(self):
        # Set the level for zuul.executor.ansible to DEBUG
        self._config['loggers']['zuul.executor.ansible']['level'] = 'DEBUG'

    @property
    def job_output_file(self) -> str:
        return self._config['handlers']['jobfile']['filename']

    @job_output_file.setter
    def job_output_file(self, filename: str):
        self._config['handlers']['jobfile']['filename'] = filename


class ServerLoggingConfig(DictLoggingConfig):

    def __init__(self, config=None, server=None):
        if not config:
            config = _DEFAULT_SERVER_LOGGING_CONFIG.copy()
        super(ServerLoggingConfig, self).__init__(config=config)
        if server:
            self.server = server

    @property
    def server(self):
        return self._server

    @server.setter
    def server(self, server):
        self._server = server
        # Add the debug and normal file handlers
        for name, handler in _DEFAULT_SERVER_FILE_HANDLERS.items():
            server_handler = handler.copy()
            server_handler['filename'] = server_handler['filename'].format(
                server=server)
            self._config['handlers'][name] = handler
        # Change everything configured to write to stdout to write to
        # log files instead. This leaves root going to console, which is
        # how the loggers infra uses work.
        for logger in self._config['loggers'].values():
            if logger['handlers'] == ['console']:
                logger['handlers'] = ['debug', 'normal']


class FileLoggingConfig(LoggingConfig):

    def __init__(self, filename):
        self._filename = filename

    def apply(self):
        logging.config.fileConfig(self._filename)


if __name__ == '__main__':
    # Use this to emit a working logging output for testing zuul_stream
    # locally.
    config = JobLoggingConfig(
        job_output_file=os.path.abspath('job-output.txt'))
    config.writeJson('logging.json')
