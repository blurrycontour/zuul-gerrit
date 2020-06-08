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

import {
  USER_ACL_REQUEST,
  USER_ACL_SUCCESS,
  USER_ACL_FAILURE,
  USER_LOGGED_IN,
  USER_LOGGED_OUT,
} from '../actions/user'

export default (state = {
  isFetching: false,
  user: null,
  token: null,
  adminTenants: []
}, action) => {
  switch (action.type) {
    case USER_LOGGED_IN:
      return {
        isFetching: true,
        user: action.user,
        token: action.user.access_token,
        adminTenants: []
      }
  case USER_LOGGED_OUT:
    return {
      isFetching: false,
      user: null,
      token: null,
      adminTenants: []
    }
    case USER_ACL_REQUEST:
      return {
        isFetching: true,
      }
  case USER_ACL_FAILURE:
    return {
      isFetching: false,
      adminTenants: []
    }
  case USER_ACL_SUCCESS:
    return {
      isFetching: false,
      adminTenants: action.adminTenants,
    }
  default:
    return state
  }
}
