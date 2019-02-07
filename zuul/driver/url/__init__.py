import logging
import requests

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from zuul.driver import Driver, TriggerInterface
from zuul.driver.url import urltrigger
from zuul.driver.url.urlmodel import URLTriggerEvent


class URLDriver(Driver, TriggerInterface):
    name = 'url'
    log = logging.getLogger("zuul.URLDriver")

    def __init__(self):
        self.apsched = BackgroundScheduler()
        self.apsched.start()
        self.tenant_jobs = {}
        self.url_attr_cache = {}

    def registerScheduler(self, scheduler):
        self.sched = scheduler

    def reconfigure(self, tenant):
        self._removeJobs(tenant)
        if not self.apsched:
            # Handle possible reuse of the driver without connection objects.
            self.apsched = BackgroundScheduler()
            self.apsched.start()
        self._addJobs(tenant)

    def _removeJobs(self, tenant):
        jobs = self.tenant_jobs.get(tenant.name, [])
        for job in jobs:
            job.remove()

    def _addJobs(self, tenant):
        jobs = []
        self.tenant_jobs[tenant.name] = jobs
        for pipeline in tenant.layout.pipelines.values():
            for ef in pipeline.manager.event_filters:
                if not isinstance(ef.trigger, urltrigger.URLTrigger):
                    continue
                parts = ef.delay.split()
                if len(parts) < 5 or len(parts) > 6:
                    self.log.error(
                        "Unable to parse time value '%s' "
                        "defined in pipeline %s" % (
                            ef.delay, pipeline.name))
                    continue
                minute, hour, dom, month, dow = parts[:5]
                if len(parts) > 5:
                    second = parts[5]
                else:
                    second = None
                trigger = CronTrigger(day=dom, day_of_week=dow, hour=hour,
                                      minute=minute, second=second)

                self.url_attr_cache[ef.url] = {ef.attribute: None}
                job = self.apsched.add_job(
                    self._onTrigger, trigger=trigger,
                    args=(tenant, pipeline.name, ef.url, ef.attribute))
                jobs.append(job)

    def _onTrigger(self, tenant, pipeline_name, url, attr):
        for project_name, pcs in tenant.layout.project_configs.items():
            # url operates on branch heads and doesn't need speculative
            # layouts to decide if it should be enqueued or not.
            # So it can be decided on cached data if it needs to run or not.
            pcst = tenant.layout.getAllProjectConfigs(project_name)
            if not [True for pc in pcst if pipeline_name in pc.pipelines]:
                continue

            self.log.debug("Fetching %s" % url)
            headers = requests.get(url).headers
            attr_value = headers.get(attr)
            if self.url_attr_cache[url][attr] is None:
                # New url - Only feed the cache
                self.log.debug(
                    "No previous state for %s only feed the "
                    "cache for: %s" % (attr, url))
                self.url_attr_cache[url][attr] = attr_value
                continue
            if attr_value == self.url_attr_cache[url][attr]:
                self.log.debug(
                    "%s attribute for %s has not changed" % (attr, url))
                continue
            self.log.info("Url at %s changed" % url)
            self.url_attr_cache[url][attr] = attr_value

            (trusted, project) = tenant.getProject(project_name)
            for branch in project.source.getProjectBranches(project, tenant):
                event = URLTriggerEvent()
                event.type = 'urlchanged'
                event.forced_pipeline = pipeline_name
                event.project_hostname = project.canonical_hostname
                event.project_name = project.name
                event.ref = 'refs/heads/%s' % branch
                event.branch = branch
                self.log.debug("Adding event %s" % event)
                self.sched.addEvent(event)

    def stop(self):
        if self.apsched:
            self.apsched.shutdown()
            self.apsched = None

    def getTrigger(self, connection_name, config=None):
        return urltrigger.URLTrigger(self, config)

    def getTriggerSchema(self):
        return urltrigger.getSchema()
