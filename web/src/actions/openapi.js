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

import * as API from '../api'
import yaml from 'js-yaml'

export const OPENAPI_FETCH_REQUEST = 'OPENAPI_FETCH_REQUEST'
export const OPENAPI_FETCH_SUCCESS = 'OPENAPI_FETCH_SUCCESS'
export const OPENAPI_FETCH_FAIL    = 'OPENAPI_FETCH_FAIL'

export const fetchOpenApiRequest = () => ({
  type: OPENAPI_FETCH_REQUEST
})

export const fetchOpenApiSuccess = (json, whiteLabel) => {
  if (whiteLabel) {
    const paths = {}
    for (let path in json.paths) {
      // Remove tenant list api
      if (path === '/api/tenants') {
        continue
      }
      // Remove tenant in path parameter
      json.paths[path].get.parameters.splice(0, 1)
      paths[path.replace('/api/tenant/{tenant}/', '/api/')] = json.paths[path]
    }
    json.paths = paths
  }
  return {
    type: OPENAPI_FETCH_SUCCESS,
    openapi: json,
  }
}

const fetchOpenApiFail = error => ({
  type: OPENAPI_FETCH_FAIL,
  error
})

const fetchOpenApi = (whiteLabel) => dispatch => {
  dispatch(fetchOpenApiRequest())
  return API.fetchOpenApi()
    .then(response => dispatch(fetchOpenApiSuccess(yaml.safeLoad(response.data), whiteLabel)))
    .catch(error => {
      dispatch(fetchOpenApiFail(error))
      setTimeout(() => {dispatch(fetchOpenApi())}, 5000)
    })
}

const shouldFetchOpenApi = openapi => {
  if (!openapi.openapi) {
    return true
  }
  if (openapi.isFetching) {
    return false
  }
  return true
}

export const fetchOpenApiIfNeeded = (force) => (dispatch, getState) => {
  const state = getState()
  if (force || shouldFetchOpenApi(state.openapi)) {
    return dispatch(fetchOpenApi(state.tenant.whiteLabel))
  }
}
