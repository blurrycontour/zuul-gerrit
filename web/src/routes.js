// Copyright 2018 Red Hat, Inc
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

import Status from './pages/status'
import Jobs from './pages/jobs'
import Builds from './pages/builds'
import Tenants from './pages/tenants'
import Stream from './pages/stream'

const routes = () => [
  {
    title: 'Status',
    to: '/status',
    component: Status,
    tenantRoute: true
  },
  {
    title: 'Jobs',
    to: '/jobs',
    component: Jobs,
    tenantRoute: true
  },
  {
    title: 'Builds',
    to: '/builds',
    component: Builds,
    tenantRoute: true
  },
  {
    to: '/stream/:buildId',
    component: Stream,
    tenantRoute: true
  },
  {
    to: '/tenants',
    component: Tenants,
    tenantRoute: false
  }
]

export { routes }
