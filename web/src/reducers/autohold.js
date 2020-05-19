// Copyright 2020 Red Hat, Inc
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

import update from 'immutability-helper'

import {

  AUTOHOLD_REQUEST_FETCH_FAIL,
  AUTOHOLD_REQUEST_FETCH_REQUEST,
  AUTOHOLD_REQUEST_FETCH_SUCCESS,

} from '../actions/autohold'


export default (state = {
  isFetching: false,
  autoholdRequests: {},
}, action) => {
  switch (action.type) {
  case AUTOHOLD_REQUEST_FETCH_REQUEST:
    return update(state, {$merge: {isFetching: true}})
  case AUTOHOLD_REQUEST_FETCH_SUCCESS:
    return update(state, {$merge: {
      isFetching: false,
      autoholdRequests: update(state.autoholdRequests, {$merge: {
        [action.autoholdRequestId]: action.autoholdRequest}})
    }})
  case AUTOHOLD_REQUEST_FETCH_FAIL:
    return update(state, {$merge: {isFetching: false}})

  default:
    return state
  }
}
