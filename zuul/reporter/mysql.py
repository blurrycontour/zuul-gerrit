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

    name = 'smtp'
    log = logging.getLogger("zuul.reporter.mysql.Reporter")

    def __init__(self, host, port, user, password, database, table):
        """Set up the reporter."""
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.table = table

        self.db = MySQLdb.connect(host=self.host,
                                  port=self.port,
                                  user=self.user,
                                  passwd=self.password,
                                  db=self.database)

    def report(self, change, message, params):
        """Send the compiled report message via smtp."""
        self.log.debug("Report change %s, params %s, message: %s" %
                       (change, params, message))

        try:
            cursor = self.db.cursor(MySQLdb.cursors.DictCursor)

            # Ensure the table exists
            cursor.execute('show tables like "%s";', self.table)
            if cursor.rowcount == 0:
                cursor.execute('create table %s (timestamp datetime, '
                               'number int, patchset int) engine=innodb;',
                               self.table)
                cursor.execute('commit;')

            cursor.execute('insert into %s (timestamp, number, patchset) '
                           'values (now(), %s, %s);',
                           (change.number, change.patchset))
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
