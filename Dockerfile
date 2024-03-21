# Copyright (c) 2019 Red Hat, Inc.
# Copyright (c) 2024 Acme Gating, LLC
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

FROM docker.io/library/node:16-bookworm as js-builder

COPY web /tmp/src
# Explicitly run the Javascript build
RUN cd /tmp/src && yarn install -d && yarn build

# We need skopeo >=v1.14.0 to negotioate with newer docker; once this
# is available in debian we can drop the custom build.
FROM golang:1.22-bookworm as go-builder

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get -y install libgpgme-dev libassuan-dev \
                       libbtrfs-dev libdevmapper-dev pkg-config && \
    git clone https://github.com/containers/skopeo /go/src/github.com/containers/skopeo &&\
    git checkout v1.15.0 &&\
    cd /go/src/github.com/containers/skopeo && make bin/skopeo

FROM docker.io/opendevorg/python-builder:3.11-bookworm as builder
ENV DEBIAN_FRONTEND=noninteractive

# Optional location of Zuul API endpoint.
ARG REACT_APP_ZUUL_API
# Optional flag to enable React Service Worker. (set to true to enable)
ARG REACT_APP_ENABLE_SERVICE_WORKER
# Kubectl/Openshift version/sha
ARG OPENSHIFT_URL=https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/4.11.20/openshift-client-linux-4.11.20.tar.gz
ARG OPENSHIFT_SHA=74f252c812932425ca19636b2be168df8fe57b114af6b114283975e67d987d11
ARG PBR_VERSION=

COPY . /tmp/src
COPY --from=js-builder /tmp/src/build /tmp/src/zuul/web/static
RUN assemble

# The wheel install method doesn't run the setup hooks as the source based
# installations do so we have to call zuul-manage-ansible here. Remove
# /root/.local/share/virtualenv after because it adds wheels into /root
# that we don't need after the install step so are a waste of space.
RUN /output/install-from-bindep \
  && zuul-manage-ansible \
  && rm -rf /root/.local/share/virtualenv \
# Install openshift
  && mkdir /tmp/openshift-install \
  && curl -L $OPENSHIFT_URL -o /tmp/openshift-install/openshift-client.tgz \
  && cd /tmp/openshift-install/ \
  && echo $OPENSHIFT_SHA /tmp/openshift-install/openshift-client.tgz | sha256sum --check \
  && tar xvfz openshift-client.tgz -C /tmp/openshift-install

FROM docker.io/opendevorg/python-base:3.11-bookworm as zuul
ENV DEBIAN_FRONTEND=noninteractive

COPY --from=builder /output/ /output
RUN /output/install-from-bindep zuul_base \
  && rm -rf /output \
  && useradd -u 10001 -m -d /var/lib/zuul -c "Zuul Daemon" zuul \
# This enables git protocol v2 which is more efficient at negotiating
# refs.  This can be removed after the images are built with git 2.26
# where it becomes the default.
  && git config --system protocol.version 2

VOLUME /var/lib/zuul
CMD ["/usr/local/bin/zuul"]

FROM zuul as zuul-executor
ENV DEBIAN_FRONTEND=noninteractive
COPY --from=builder /usr/local/lib/zuul/ /usr/local/lib/zuul
COPY --from=builder /tmp/openshift-install/oc /usr/local/bin/oc
COPY --from=go-builder /go/src/github.com/containers/skopeo/bin/skopeo /usr/local/bin/skopeo
# The oc and kubectl binaries are large and have the same hash.
# Copy them only once and use a symlink to save space.
RUN ln -s /usr/local/bin/oc /usr/local/bin/kubectl

CMD ["/usr/local/bin/zuul-executor", "-f"]

FROM zuul as zuul-fingergw
CMD ["/usr/local/bin/zuul-fingergw", "-f"]

FROM zuul as zuul-merger
CMD ["/usr/local/bin/zuul-merger", "-f"]

FROM zuul as zuul-scheduler
CMD ["/usr/local/bin/zuul-scheduler", "-f"]

FROM zuul as zuul-web
CMD ["/usr/local/bin/zuul-web", "-f"]
