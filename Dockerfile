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

# Optional location of Zuul API endpoint.
ARG REACT_APP_ZUUL_API
# Optional flag to enable React Service Worker. (set to true to enable)
ARG REACT_APP_ENABLE_SERVICE_WORKER

# Optional location of packages
ARG PACKAGE_MIRROR

RUN [ -n "${PACKAGE_MIRROR}" ] || exit 0 \
  && echo "deb [ trusted=yes ] http://${PACKAGE_MIRROR}/debian buster main" > /etc/apt/sources.list \
  && echo "deb [ trusted=yes ] http://${PACKAGE_MIRROR}/debian buster-updates main" >> /etc/apt/sources.list \
  && echo "deb [ trusted=yes ] http://${PACKAGE_MIRROR}/debian buster-backports main" >> /etc/apt/sources.list

COPY . /tmp/src
RUN /tmp/src/tools/install-js-tools.sh
RUN assemble

# The wheel install method doesn't run the setup hooks as the source based
# installations do so we have to call zuul-manage-ansible here.
RUN /output/install-from-bindep && zuul-manage-ansible


FROM opendevorg/python-base as zuul

COPY --from=builder /output/ /output
RUN echo "deb http://ftp.debian.org/debian buster-backports main" >> /etc/apt/sources.list \
  && if [ -n "${PACKAGE_MIRROR}" ]; then \
      mv /etc/apt/sources.list /etc/apt/sources.list.bak \
      && echo "deb [ trusted=yes ] http://${PACKAGE_MIRROR}/debian buster main" > /etc/apt/sources.list \
      && echo "deb [ trusted=yes ] http://${PACKAGE_MIRROR}/debian buster-updates main" >> /etc/apt/sources.list \
      && echo "deb [ trusted=yes ] http://${PACKAGE_MIRROR}/debian buster-backports main" >> /etc/apt/sources.list \
  fi \
  && apt-get update \
  && apt-get install -t buster-backports -y bubblewrap \
  && /output/install-from-bindep \
  && pip install --cache-dir=/output/wheels -r /output/zuul_base/requirements.txt \
  && rm -rf /output \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && if [ -n "${PACKAGE_MIRROR}" ]; then \
    rm  /etc/apt/apt.conf.d/99unauthenticated \
    && mv /etc/apt/sources.list.bak /etc/apt/sources.list; \
  fi

VOLUME /var/lib/zuul
CMD ["/usr/local/bin/zuul"]

FROM zuul as zuul-executor
COPY --from=builder /usr/local/lib/zuul/ /usr/local/lib/zuul

CMD ["/usr/local/bin/zuul-executor"]

FROM zuul as zuul-fingergw
CMD ["/usr/local/bin/zuul-fingergw"]

FROM zuul as zuul-merger
CMD ["/usr/local/bin/zuul-merger"]

FROM zuul as zuul-scheduler
CMD ["/usr/local/bin/zuul-scheduler"]

FROM zuul as zuul-web
CMD ["/usr/local/bin/zuul-web"]
