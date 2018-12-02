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
import { addApiError } from './errors'

export const REQUEST_INFO = 'REQUEST_INFO'
export const RECEIVE_INFO = 'RECEIVE_INFO'

export const requestInfo = () => ({
  type: REQUEST_INFO
})

export const receiveInfo = json => ({
  type: RECEIVE_INFO,
  info: json.info,
  receivedAt: Date.now()
})

const fetchInfo = () => dispatch => {
  dispatch(requestInfo())
  return API.fetchInfo()
    .then(response => dispatch(receiveInfo(response.data)))
    .catch(error => {
      dispatch(addApiError(error))
      setTimeout(() => {dispatch(fetchInfo())}, 5000)
    })
}

const shouldFetchInfo = state => {
  const info = state.info
  if (!info) {
    return true
  }
  if (info.isFetching) {
    return false
  }
  return true
}

export const fetchInfoIfNeeded = () => (dispatch, getState) => {
  if (shouldFetchInfo(getState())) {
    return dispatch(fetchInfo())
  }
}
