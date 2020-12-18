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

import initialState from './initialState'

import {
  USERMANAGER_CREATE,
  USERMANAGER_FAIL,
  USERMANAGER_SUCCESS,
} from '../actions/auth'

export default (state = initialState.auth, action) => {
  switch (action.type) {
    case USERMANAGER_CREATE:
      return {
        isFetching: true,
        userManagerConfig: null,
        capabilities: null,
      }
    case USERMANAGER_SUCCESS:
      return {
        isFetching: false,
        userManagerConfig: action.userManagerConfig,
        capabilities: action.capabilities
      }
    case USERMANAGER_FAIL:
      return {
        isFetching: false,
        userManager: null,
        capabilities: null,
      }
    default:
      return state
  }
}
