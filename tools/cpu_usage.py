import pprint
import re

# example log string:
# noqa
# 2018-10-26 16:14:47,527 INFO zuul.nodepool: Nodeset <NodeSet two-centos-7-nodes [<Node 0000058431 ('primary',):centos-7>, <Node 0000058468 ('secondary',):centos-7>]> with 2 nodes was in use for 6241.08082151413 seconds for build <Build 530c4ca7af9e44dcb535e7074258e803 of tripleo-ci-centos-7-scenario008-multinode-oooq-container voting:False on <Worker ze05.openstack.org>> for project openstack/tripleo-quickstart-extras

# noqa
r = re.compile(r'\d+-\d+-\d+ \d\d:\d\d:\d\d,\d\d\d INFO zuul.nodepool: Nodeset <.*> with (?P<nodes>\d+) nodes was in use for (?P<secs>\d+(.[\d\-e]+)?) seconds for build <Build \w+ of (?P<job>[^\s]+) voting:\w+ on .* for project (?P<project>[^\s]+)')

projects = {}
with open('/var/log/zuul/debug.log') as f:
    for line in f:
        if 'nodes was in use for' in line:
            m = r.match(line)
            if not m:
                print(line)
                continue
            g = m.groupdict()
            project = g['project']
            secs = float(g['secs'])
            nodes = int(g['nodes'])
            job = g['job']
            if project not in projects:
                projects[project] = {}
                projects[project]['total'] = 0.0
            cpu_time = nodes * secs
            projects[project]['total'] += cpu_time
            if job not in projects[project]:
                projects[project][job] = 0.0
            projects[project][job] += cpu_time


#pprint.pprint(projects)
sortable = []
for project in projects:
    sortable.append((project, projects[project]['total']))

sortable.sort(key=lambda x: x[1], reverse=True)

for project, total in sortable:
    print('%s: %s' % (project, total))

