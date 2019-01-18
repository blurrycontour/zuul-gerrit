#!/bin/bash
# Copyright 2017 Red Hat, Inc.
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

SUDO=${INSTALL_JS_TOOLS_SUDO_CMD:-sudo}

if type apt-get; then
    # Install https transport - otherwise apt-get HANGS on https urls
    $SUDO apt-get update
    $SUDO apt-get install apt-transport-https
    # Install recent NodeJS repo
    curl -sS https://deb.nodesource.com/gpgkey/nodesource.gpg.key | $SUDO apt-key add -
    echo "deb https://deb.nodesource.com/node_8.x xenial main" | $SUDO tee /etc/apt/sources.list.d/nodesource.list
    # Install yarn repo
    curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | $SUDO apt-key add -
    echo "deb https://dl.yarnpkg.com/debian/ stable main" | $SUDO tee /etc/apt/sources.list.d/yarn.list
    $SUDO apt-get update
    $SUDO DEBIAN_FRONTEND=noninteractive \
        apt-get -q --option "Dpkg::Options::=--force-confold" --assume-yes \
        install nodejs yarn
elif type yum; then
    $SUDO curl https://dl.yarnpkg.com/rpm/yarn.repo -o /etc/yum.repos.d/yarn.repo
    $SUDO $(dirname $0)/install-js-repos-rpm.sh
    $SUDO yum -y install nodejs yarn
elif type brew; then
    brew install nodejs yarn
else
    echo "Unsupported platform"
fi
