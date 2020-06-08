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

import { combineReducers } from 'redux'

import auth from './auth'
import configErrors from './configErrors'
import change from './change'
import errors from './errors'
import build from './build'
import info from './info'
import job from './job'
import jobs from './jobs'
import labels from './labels'
import logfile from './logfile'
import nodes from './nodes'
import openapi from './openapi'
import project from './project'
import projects from './projects'
import status from './status'
import tenant from './tenant'
import tenants from './tenants'
import timezone from './timezone'
//import { reducer as userInfo } from 'redux-oidc';
import user from './user'

const reducers = {
  auth,
  build,
  change,
  configErrors,
  errors,
  info,
  job,
  jobs,
  labels,
  logfile,
  nodes,
  openapi,
  user,
  project,
  projects,
  status,
  tenant,
  tenants,
  timezone,
}

export default combineReducers(reducers)
