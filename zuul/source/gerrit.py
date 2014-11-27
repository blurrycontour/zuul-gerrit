# Copyright 2012 Hewlett-Packard Development Company, L.P.
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
import time
from zuul.model import Change, Ref, NullChange
from zuul.source import BaseSource


class GerritSource(BaseSource):
    name = 'gerrit'
    log = logging.getLogger("zuul.source.Gerrit")
    replication_timeout = 300
    replication_retry_interval = 5

    def _getInfoRefs(self, project):
        return self.connection._getInfoRefs(project)

    def getRefSha(self, project, ref):
        refs = {}
        try:
            refs = self._getInfoRefs(project)
        except:
            self.log.exception("Exception looking for ref %s" %
                               ref)
        sha = refs.get(ref, '')
        return sha

    def waitForRefSha(self, project, ref, old_sha=''):
        # Wait for the ref to show up in the repo
        start = time.time()
        while time.time() - start < self.replication_timeout:
            sha = self.getRefSha(project.name, ref)
            if old_sha != sha:
                return True
            time.sleep(self.replication_retry_interval)
        return False

    def isMerged(self, change, head=None):
        self.log.debug("Checking if change %s is merged" % change)
        if not change.number:
            self.log.debug("Change has no number; considering it merged")
            # Good question.  It's probably ref-updated, which, ah,
            # means it's merged.
            return True

        data = self.connection.query(change.number)
        change._data = data
        change.is_merged = self._isMerged(change)
        if not head:
            return change.is_merged
        if not change.is_merged:
            return False

        ref = 'refs/heads/' + change.branch
        self.log.debug("Waiting for %s to appear in git repo" % (change))
        if self.waitForRefSha(change.project, ref, change._ref_sha):
            self.log.debug("Change %s is in the git repo" %
                           (change))
            return True
        self.log.debug("Change %s did not appear in the git repo" %
                       (change))
        return False

    def _isMerged(self, change):
        data = change._data
        if not data:
            return False
        status = data.get('status')
        if not status:
            return False
        self.log.debug("Change %s status: %s" % (change, status))
        if status == 'MERGED':
            return True
        return False

    def canMerge(self, change, allow_needs):
        if not change.number:
            self.log.debug("Change has no number; considering it merged")
            # Good question.  It's probably ref-updated, which, ah,
            # means it's merged.
            return True
        data = change._data
        if not data:
            return False
        if 'submitRecords' not in data:
            return False
        try:
            for sr in data['submitRecords']:
                if sr['status'] == 'OK':
                    return True
                elif sr['status'] == 'NOT_READY':
                    for label in sr['labels']:
                        if label['status'] == 'OK':
                            continue
                        elif label['status'] in ['NEED', 'REJECT']:
                            # It may be our own rejection, so we ignore
                            if label['label'].lower() not in allow_needs:
                                return False
                            continue
                        else:
                            # IMPOSSIBLE
                            return False
                else:
                    # CLOSED, RULE_ERROR
                    return False
        except:
            self.log.exception("Exception determining whether change"
                               "%s can merge:" % change)
            return False
        return True

    def postConfig(self):
        pass

    def getChange(self, event, project):
        if event.change_number:
            refresh = False
            if event._needs_refresh:
                refresh = True
                event._needs_refresh = False
            change = self._getChange(event.change_number, event.patch_number,
                                     refresh=refresh)
        elif event.ref:
            change = Ref(project)
            change.ref = event.ref
            change.oldrev = event.oldrev
            change.newrev = event.newrev
            change.url = self.getGitwebUrl(project, sha=event.newrev)
        else:
            change = NullChange(project)
        return change

    def _getChange(self, number, patchset, refresh=False):
        key = '%s,%s' % (number, patchset)
        change = None
        if key in self.connection._change_cache:
            change = self.connection._change_cache.get(key)
            if not refresh:
                return change
        if not change:
            change = Change(None)
            change.number = number
            change.patchset = patchset
        key = '%s,%s' % (change.number, change.patchset)
        self.connection._change_cache[key] = change
        try:
            self.updateChange(change)
        except Exception:
            del self.connection._change_cache[key]
            raise
        return change

    def getProjectOpenChanges(self, project):
        # This is a best-effort function in case Gerrit is unable to return
        # a particular change.  It happens.
        query = "project:%s status:open" % (project.name,)
        self.log.debug("Running query %s to get project open changes" %
                       (query,))
        data = self.connection.simpleQuery(query)
        changes = []
        for record in data:
            try:
                changes.append(
                    self._getChange(record['number'],
                                    record['currentPatchSet']['number']))
            except Exception:
                self.log.exception("Unable to query change %s" %
                                   (record.get('number'),))
        return changes

    def updateChange(self, change):
        self.log.info("Updating information for %s,%s" %
                      (change.number, change.patchset))
        data = self.connection.query(change.number)
        change._data = data

        if change.patchset is None:
            change.patchset = data['currentPatchSet']['number']

        if 'project' not in data:
            raise Exception("Change %s,%s not found" % (change.number,
                                                        change.patchset))
        change.project = self.sched.getProject(data['project'])
        change.branch = data['branch']
        change.url = data['url']
        max_ps = 0
        change.files = []
        for ps in data['patchSets']:
            if ps['number'] == change.patchset:
                change.refspec = ps['ref']
                for f in ps.get('files', []):
                    change.files.append(f['file'])
            if int(ps['number']) > int(max_ps):
                max_ps = ps['number']
        if max_ps == change.patchset:
            change.is_current_patchset = True
        else:
            change.is_current_patchset = False

        change.is_merged = self._isMerged(change)
        change.approvals = data['currentPatchSet'].get('approvals', [])
        change.open = data['open']
        change.status = data['status']
        change.owner = data['owner']

        if change.is_merged:
            # This change is merged, so we don't need to look any further
            # for dependencies.
            return change

        change.needs_change = None
        if 'dependsOn' in data:
            parts = data['dependsOn'][0]['ref'].split('/')
            dep_num, dep_ps = parts[3], parts[4]
            dep = self._getChange(dep_num, dep_ps)
            if not dep.is_merged:
                change.needs_change = dep

        change.needed_by_changes = []
        if 'neededBy' in data:
            for needed in data['neededBy']:
                parts = needed['ref'].split('/')
                dep_num, dep_ps = parts[3], parts[4]
                dep = self._getChange(dep_num, dep_ps)
                if not dep.is_merged and dep.is_current_patchset:
                    change.needed_by_changes.append(dep)

        return change

    def getGitUrl(self, project):
        return self.connection.getGitUrl(project)

    def getGitwebUrl(self, project, sha=None):
        return self.connection.getGitwebUrl(project, sha)

    def maintainCache(self, relevant):
        self.connection.maintainCache(relevant)
