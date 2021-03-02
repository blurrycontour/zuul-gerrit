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
  USER_ACL_REQUEST,
  USER_ACL_SUCCESS,
  USER_ACL_FAILURE,
  USER_LOGGED_IN,
  USER_LOGGED_OUT,
  getToken,
} from '../actions/user'

const stored_user = localStorage.getItem('user')

let default_user
let default_token
if (stored_user === null) {
  default_user = null
  default_token = null
} else {
  default_user = JSON.parse(stored_user)
  default_token = getToken(default_user)
}

export default (state = {
  isFetching: false,
  user: default_user,
  token: default_token,
  scope: [],
  isAdmin: false
}, action) => {
  switch (action.type) {
    case USER_LOGGED_IN:
      localStorage.setItem('user', JSON.stringify(action.user))
      return {
        isFetching: true,
        user: action.user,
        token: action.token,
        scope: [],
        isAdmin: false
      }
  case USER_LOGGED_OUT:
    localStorage.removeItem('user')
    return {
      isFetching: false,
      user: null,
      token: null,
      scope: [],
      isAdmin: false
    }
    case USER_ACL_REQUEST:
      return update(state, {$merge: {isFetching: true}})
  case USER_ACL_FAILURE:
    return update(state, {$merge: {isFetching: false,
                                   scope: [],
                                   isAdmin: false}})
  case USER_ACL_SUCCESS:
    return update(state, {$merge: {isFetching: false,
                                   scope: action.scope,
                                   isAdmin: action.isAdmin}})
  default:
    return state
  }
}
