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

import {
  CONFIGERRORS_FETCH_FAIL,
  CONFIGERRORS_FETCH_REQUEST,
  CONFIGERRORS_FETCH_SUCCESS,
  CONFIGERRORS_CLEAR
} from '../actions/configErrors'

export default (state = {
  errors: [],
  isFetching: false,
  ready: false,
  tenant: '',
}, action) => {
  switch (action.type) {
    case CONFIGERRORS_FETCH_REQUEST:
      return {
        isFetching: true,
        ready: false,
        tenant: action.tenant,
        errors: [],
      }
    case CONFIGERRORS_FETCH_SUCCESS:
      if (action.tenant === state.tenant) {
        return {
          isFetching: false,
          ready: true,
          tenant: action.tenant,
          errors: action.errors,
        }
      } else {
        return state
      }
    case CONFIGERRORS_FETCH_FAIL:
      if (action.tenant === state.tenant) {
        return {
          isFetching: false,
          ready: false,
          tenant: action.tenant,
          errors: [],
        }
      } else {
        return state
      }
    case CONFIGERRORS_CLEAR:
      return {
        isFetching: false,
        ready: false,
        tenant: '',
        errors: [],
      }
    default:
      return state
  }
}
