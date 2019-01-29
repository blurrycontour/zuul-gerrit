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

import {
  CONFIG_FETCH_FAIL,
  CONFIG_FETCH_REQUEST,
  CONFIG_FETCH_SUCCESS
} from '../actions/config'

import update from 'immutability-helper'

export default (state = {
  isFetching: false,
  config: {},
}, action) => {
  switch (action.type) {
    case CONFIG_FETCH_REQUEST:
      return {
        isFetching: true,
        config: state.config,
      }
    case CONFIG_FETCH_SUCCESS:
      return {
        isFetching: false,
        config: update(
          state.config, {$merge: {[action.tenant]: action.config}}),
      }
    case CONFIG_FETCH_FAIL:
      return {
        isFetching: false,
        config: state.config,
      }
    default:
      return state
  }
}
