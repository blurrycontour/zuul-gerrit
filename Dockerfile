# Copyright (c) 2019 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM opendevorg/python-builder as builder

COPY . /tmp/src
RUN /tmp/src/tools/docker-install-js-tools.sh
RUN assemble

FROM opendevorg/python-base as zuul-base

COPY --from=builder /output/ /output
COPY tools/018D05F5.gpg /tmp/bubblewrap.gpg
RUN apt-get update \
  && apt-get install -y gnupg2 \
  && apt-key add /tmp/bubblewrap.gpg \
  && echo "deb http://ppa.launchpad.net/openstack-ci-core/bubblewrap/ubuntu xenial main" > \
       /etc/apt/sources.list.d/openstack-ci-core-ubuntu-bubblewrap-xenial.list \
  && rm /tmp/bubblewrap.gpg \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*
RUN /output/install-from-bindep \
  && pip install --cache-dir=/output/wheels -r /output/zuul_base/requirements.txt \
  && rm -rf /output

FROM zuul-base as zuul
CMD ["/usr/local/bin/zuul"]

FROM zuul-base as zuul-bwrap
CMD ["/usr/local/bin/zuul-bwrap"]

FROM zuul-base as zuul-executor
COPY --from=builder /output/zuul_executor/requirements.txt /tmp/requirements.txt
RUN pip install --cache-dir=/output/wheels -r /tmp/requirements.txt \
  && rm /tmp/requirements.txt
CMD ["/usr/local/bin/zuul-executor"]

FROM zuul-base as zuul-fingergw
CMD ["/usr/local/bin/zuul-fingergw"]

FROM zuul-base as zuul-merger
CMD ["/usr/local/bin/zuul-merger"]

FROM zuul-base as zuul-migrate
CMD ["/usr/local/bin/zuul-migrate"]

FROM zuul-base as zuul-scheduler
CMD ["/usr/local/bin/zuul-scheduler"]

FROM zuul-base as zuul-web
CMD ["/usr/local/bin/zuul-web"]
