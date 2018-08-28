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

import Status from './pages/Status'
import Jobs from './pages/Jobs'
import Build from './pages/Build'
import Builds from './pages/Builds'
import Tenants from './pages/Tenants'
import Stream from './pages/Stream'

// The Route object are created in the App component.
// Object with a title are created in the menu.
// Object with globalRoute are not tenant scoped.
// Remember to update the api getHomepageUrl subDir list for route with params
const routes = () => [
  {
    title: 'Status',
    to: '/status',
    component: Status
  },
  {
    title: 'Jobs',
    to: '/jobs',
    component: Jobs
  },
  {
    title: 'Builds',
    to: '/builds',
    component: Builds
  },
  {
    to: '/stream/:buildId',
    component: Stream
  },
  {
    to: '/build/:buildId',
    component: Build
  },
  {
    to: '/tenants',
    component: Tenants,
    globalRoute: true
  }
]

export { routes }
