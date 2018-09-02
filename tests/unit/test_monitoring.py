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

import requests

from tests.base import ZuulTestCase


class BaseTestPrometheus(ZuulTestCase):
    tenant_config_file = 'config/single-tenant/main.yaml'

    def get_metrics(self):
        r = requests.get(
            "http://localhost:%d" % self.prometheus_server.port)
        metrics = {}
        for line in r.text.split('\n'):
            if not line or line.startswith("#"):
                continue
            key, value = line.split()
            metrics[key] = value
        return metrics


class TestPrometheus(BaseTestPrometheus):
    def test_prometheus_process_metrics(self):
        metrics = self.get_metrics()
        self.assertIn("process_resident_memory_bytes", metrics)
        self.assertIn("process_open_fds", metrics)

    def test_prometheus_executors_metrics(self):
        metrics = self.get_metrics()
        self.assertIn("sensor_builds_running", metrics)

    def test_prometheus_scheduler_metrics(self):
        metrics = self.get_metrics()
        self.assertIn("sched_reconfigure_seconds", metrics)
