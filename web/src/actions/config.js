/* global Promise */
// Copyright 2019 Red Hat, Inc
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

import * as API from '../api'

export const CONFIG_FETCH_REQUEST = 'CONFIG_FETCH_REQUEST'
export const CONFIG_FETCH_SUCCESS = 'CONFIG_FETCH_SUCCESS'
export const CONFIG_FETCH_FAIL = 'CONFIG_FETCH_FAIL'

export const requestConfig = () => ({
  type: CONFIG_FETCH_REQUEST
})

export const receiveConfig = (tenant, json) => ({
  type: CONFIG_FETCH_SUCCESS,
  tenant: tenant,
  config: json,
  receivedAt: Date.now()
})

const failedConfig = error => ({
  type: CONFIG_FETCH_FAIL,
  error
})

const fetchConfig = (tenant) => dispatch => {
  dispatch(requestConfig())
  return API.fetchConfig(tenant.apiPrefix)
    .then(response => dispatch(receiveConfig(tenant.name, response.data)))
    .catch(error => dispatch(failedConfig(error)))
}

const shouldFetchConfig = (tenant, state) => {
  const config = state.config.config[tenant.name]
  if (!config) {
    return true
  }
  if (config.isFetching) {
    return false
  }
  return false
}

export const fetchConfigIfNeeded = (tenant, force) => (dispatch, getState) => {
  if (force || shouldFetchConfig(tenant, getState())) {
    return dispatch(fetchConfig(tenant))
  }
  return Promise.resolve()
}
