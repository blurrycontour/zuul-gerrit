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

import {fetchBuild, fetchBuildManifest} from './build'

export const LOGFILE_FETCH_SUCCESS = 'LOGFILE_FETCH_SUCCESS'
export const LOGFILE_FETCH_FAIL = 'LOGFILE_FETCH_FAIL'

const receiveLogfile = (url) => ({
  type: LOGFILE_FETCH_SUCCESS,
  url: url
})

const failedLogfile = error => ({
  type: LOGFILE_FETCH_FAIL,
  error
})

const fetchLogfile = (buildId, file, state, force) => dispatch => {
  const build = state.build.builds[buildId]
  const item = build.manifest.index['/' + file]

  if (!item)
    dispatch(failedLogfile(null))
  const url = build.log_url + file
  console.log('receive url', url)
  dispatch(receiveLogfile(url))
}

export const fetchLogfileIfNeeded = (tenant, buildId, file, force) => (dispatch, getState) => {
  dispatch(fetchBuild(tenant, buildId, getState(), force))
    .then(() => {
      dispatch(fetchBuildManifest(buildId, getState(), force))
        .then(() => {
          dispatch(fetchLogfile(buildId, file, getState(), force))
        })
    })
}
