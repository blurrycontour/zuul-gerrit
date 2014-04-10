# Copyright 2014 Rackspace Australia
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
import MySQLdb


class Reporter(object):
    """Logs reports in a MySQL database"""

    name = 'mysql'
    log = logging.getLogger("zuul.reporter.mysql.Reporter")

    def __init__(self, host, port, user, password, database, table):
        """Set up the reporter."""
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.table = table
        self.cursor = None

    def connect(self):
        """Try to connect to MySQL and create the results table if it doesn't
        already exist."""
        db = MySQLdb.connect(host=self.host,
                             port=self.port,
                             user=self.user,
                             passwd=self.password,
                             db=self.database)
        self.cursor = db.cursor(MySQLdb.cursors.DictCursor)

        self.cursor.execute('show tables like "%s";' % self.table)
        if self.cursor.rowcount == 0:
            self.cursor.execute('create table %s (timestamp datetime, '
                                'number int, patchset int, score tinyint) '
                                'engine=innodb;'
                                % self.table)
            self.cursor.execute('commit;')

    def report(self, change, message, params, retries=1):
        """Insert the report into MySQL"""
        self.log.debug("Report change %s, params %s, message: %s to %s:%s" %
                       (change, params, message, self.database, self.table))

        try:
            if not self.cursor:
                self.connect()
            self.cursor.execute('insert into %s '
                                '(timestamp, number, patchset, score) '
                                'values (now(), %s, %s, %s);' % self.table,
                                (change.number, change.patchset,
                                 params['score'],))
            self.cursor.execute('commit;')

        except Exception as e:
            self.cursor = None
            self.log.warning('Could not report to mysql: %s, '
                             '%d retries remaining' % (e, retries))
            if retries > 0:
                # Keep trying until we're out of retries
                retries -= 1
                return self.report(change, message, params, retries)
            return 'Could not report to mysql: %s' % e

        return

    def getSubmitAllowNeeds(self, params):
        """Get a list of code review labels that are allowed to be
        "needed" in the submit records for a change, with respect
        to this queue.  In other words, the list of review labels
        this reporter itself is likely to set before submitting.
        """
        return []
