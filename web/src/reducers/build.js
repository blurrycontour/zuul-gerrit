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
  BUILD_FETCH_FAIL,
  BUILD_FETCH_REQUEST,
  BUILD_FETCH_SUCCESS,
  BUILD_RESULT_FETCH_SUCCESS
} from '../actions/build'

export default (state = {
  isFetching: false,
  build: null
}, action) => {
  switch (action.type) {
    case BUILD_FETCH_REQUEST:
      return {
        isFetching: true,
        build: null,
      }
    case BUILD_FETCH_SUCCESS:
      return {
        isFetching: false,
        build: action.build,
      }
    case BUILD_FETCH_FAIL:
      return {
        isFetching: false,
        build: null,
      }
    case BUILD_RESULT_FETCH_SUCCESS:
      return update(state, {build: {$merge: {output: action.result}}})
    default:
      return state
  }
}
