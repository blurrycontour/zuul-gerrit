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

export const AUTOHOLD_REQUEST_FETCH_REQUEST = 'AUTOHOLD_REQUEST_FETCH_REQUEST'
export const AUTOHOLD_REQUEST_FETCH_SUCCESS = 'AUTOHOLD_REQUEST_FETCH_SUCCESS'
export const AUTOHOLD_REQUEST_FETCH_FAIL =    'AUTOHOLD_REQUEST_FETCH_FAIL'


export const requestAutoholdRequest = () => ({
  type: AUTOHOLD_REQUEST_FETCH_REQUEST
})

export const receiveAutoholdRequest = (autoholdRequestId, autoholdRequest) => ({
  type: AUTOHOLD_REQUEST_FETCH_SUCCESS,
  autoholdRequestId: autoholdRequestId,
  autoholdRequest: autoholdRequest,
  receivedAt: Date.now()
})

const failedAutoholdRequest = error => ({
  type: AUTOHOLD_REQUEST_FETCH_FAIL,
  error
})

const fetchAutoholdRequest = (tenant, autoholdRequestId) => dispatch => {
  dispatch(requestAutoholdRequest())
  return API.fetchAutohold(tenant.apiPrefix, autoholdRequestId)
    .then(response => {
      dispatch(receiveAutoholdRequest(autoholdRequestId, response.data))
    })
    .catch(error => dispatch(failedAutoholdRequest(error)))
}

const shouldFetchAutoholdRequest = (autoholdRequestId, state) => {
  const autoholdRequest = state.autohold.autoholdRequests[autoholdRequestId]
  if (!autoholdRequest) {
    return true
  }
  if (autoholdRequest.isFetching) {
    return false
  }
  return false
}

export const fetchAutoholdRequestIfNeeded = (tenant, autoholdRequestId, force) => (
  dispatch, getState) => {
    if (force || shouldFetchAutoholdRequest(autoholdRequestId, getState())) {
      return dispatch(fetchAutoholdRequest(tenant, autoholdRequestId))
    }
}
