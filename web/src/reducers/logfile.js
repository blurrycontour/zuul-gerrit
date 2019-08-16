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

import update from 'immutability-helper'

import {
  LOGFILE_FETCH_FAIL,
  LOGFILE_FETCH_REQUEST,
  LOGFILE_FETCH_SUCCESS,
} from '../actions/logfile'


export default (state = {
  isFetching: false,
  buildId: null,
  buildLogfiles: {},
}, action) => {
  switch (action.type) {
    case LOGFILE_FETCH_REQUEST:
      if (action.buildId !== state.buildId) {
        state = update(state, {$merge: {buildId: action.buildId,
                                        buildLogfiles: {}}})
      }
      return update(state, {$merge: {isFetching: true}})
    case LOGFILE_FETCH_SUCCESS:
      if (action.buildId === state.buildId) {
        console.log(state.buildLogfiles)
        state.buildLogfiles = update(
          state.buildLogfiles, {$merge: {[action.file]: action.data}})
        console.log(state.buildLogfiles)
      }
      return update(state, {$merge: {isFetching: false}})
    case LOGFILE_FETCH_FAIL:
      return update(state, {$merge: {isFetching: false}})
    default:
      return state
  }
}
