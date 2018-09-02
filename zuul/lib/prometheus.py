# Copyright 2018 Red Hat, Inc.
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

from typing import Dict  # flake8: noqa

try:
    import prometheus_client  # type: ignore
except ImportError:
    def noop(func):
        return func

    class FakeMetrics:
        # Fake client when library isn't installed
        def __init__(*args):
            pass

        def time(self):
            return noop

        def set(*args):
            pass

        def inc(*args):
            pass

    class prometheus_client:  # type: ignore
        Counter = FakeMetrics
        Gauge = FakeMetrics
        Summary = FakeMetrics


# Keep metrics references as global to prevent test errors:
# "ValueError: Duplicated timeseries in CollectorRegistry"
metrics = {}  # type: Dict[str, object]


def Gauge(name, description):
    if name in metrics:
        return metrics[name]
    return metrics.setdefault(name, prometheus_client.Gauge(name, description))


def Counter(name, description):
    if name in metrics:
        return metrics[name]
    return metrics.setdefault(
        name, prometheus_client.Counter(name, description))


def Summary(name, description):
    if name in metrics:
        return metrics[name]
    return metrics.setdefault(
        name, prometheus_client.Summary(name, description))
