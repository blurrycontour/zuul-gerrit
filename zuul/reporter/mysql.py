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

    def report(self, change, message, params):
        """Insert the report into MySQL"""
        self.log.debug("Report change %s, params %s, message: %s to %s:%s" %
                       (change, params, message, self.database, self.table))

        try:
            db = MySQLdb.connect(host=self.host,
                                 port=self.port,
                                 user=self.user,
                                 passwd=self.password,
                                 db=self.database)
            cursor = db.cursor(MySQLdb.cursors.DictCursor)

            # NOTE(mikal): these need to not use safe sql injection, because
            # then the table name is incorrectly quoted.
            cursor.execute('show tables like "%s";' % self.table)
            if cursor.rowcount == 0:
                cursor.execute('create table %s (timestamp datetime, '
                               'number int, patchset int, score tinyint) '
                               'engine=innodb;'
                               % self.table)

            cursor.execute('insert into %s '
                           '(timestamp, number, patchset, score) '
                           'values (now(), %s, %s, %s);' % self.table,
                           (change.number, change.patchset, params['score'],))
            cursor.execute('commit;')

        except Exception as e:
            return 'Could not report to mysql: %s' % e

        return

    def getSubmitAllowNeeds(self, params):
        """Get a list of code review labels that are allowed to be
        "needed" in the submit records for a change, with respect
        to this queue.  In other words, the list of review labels
        this reporter itself is likely to set before submitting.
        """
        return []
