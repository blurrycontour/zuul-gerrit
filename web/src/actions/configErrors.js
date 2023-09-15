// Copyright 2018 Red Hat, Inc
// Copyright 2023 Acme Gating, LLC
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

import { fetchConfigErrors } from '../api'

export const CONFIGERRORS_FETCH_REQUEST = 'CONFIGERRORS_FETCH_REQUEST'
export const CONFIGERRORS_FETCH_SUCCESS = 'CONFIGERRORS_FETCH_SUCCESS'
export const CONFIGERRORS_FETCH_FAIL = 'CONFIGERRORS_FETCH_FAIL'
export const CONFIGERRORS_CLEAR = 'CONFIGERRORS_CLEAR'

export const requestConfigErrors = (tenant) => ({
  type: CONFIGERRORS_FETCH_REQUEST,
  tenant: tenant,
})

export const receiveConfigErrors = (tenant, json) => ({
  type: CONFIGERRORS_FETCH_SUCCESS,
  tenant: tenant,
  errors: json,
  receivedAt: Date.now()
})

const failedConfigErrors = (tenant, error) => ({
  type: CONFIGERRORS_FETCH_FAIL,
  tenant: tenant,
  error
})


export function fetchConfigErrorsAction (tenant) {
  return (dispatch, getState) => {
    const state = getState()
    if (state.configErrors.isFetching && tenant.name === state.configErrors.tenant) {
      return Promise.resolve()
    }
    dispatch(requestConfigErrors(tenant.name))
    return fetchConfigErrors(tenant.apiPrefix)
      .then(response => dispatch(receiveConfigErrors(tenant.name, response.data)))
      .catch(error => dispatch(failedConfigErrors(tenant.name, error)))
  }
}

export function clearConfigErrorsAction () {
  return (dispatch) => {
    dispatch({type: 'CONFIGERRORS_CLEAR'})
  }
}
