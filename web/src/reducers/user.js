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
  USER_LOGGED_IN,
  USER_IN_LOCALSTORAGE,
  USER_LOGGED_OUT,
} from '../actions/user'
import {
  USER_ACL_REQUEST,
  USER_ACL_SUCCESS,
  USER_ACL_FAIL,
} from '../actions/auth'

export default (state = {
  isFetching: false,
  user: null,
  token: null,
  scope: [],
  isAdmin: false
}, action) => {
  switch (action.type) {
    case USER_LOGGED_IN: {
      let user_stringified = JSON.stringify(action.user)
      localStorage.setItem('zuul_user', user_stringified)
      return {
        isFetching: false,
        user: action.user,
        token: action.token,
        scope: [],
        isAdmin: false
      }
    }
    case USER_IN_LOCALSTORAGE:
      return {
        isFetching: false,
        user: action.user,
        token: action.token,
        scope: [],
        isAdmin: false
      }
    case USER_LOGGED_OUT:
      localStorage.removeItem('zuul_user')
      return {
        isFetching: false,
        user: null,
        token: null,
        scope: [],
        isAdmin: false
      }
    case USER_ACL_REQUEST:
      return { ...state, isFetching: true }
    case USER_ACL_FAIL:
      return {
        ...state,
        isFetching: false,
        scope: [],
        isAdmin: false
      }
    case USER_ACL_SUCCESS:
      return {
        ...state,
        isFetching: false,
        scope: action.scope,
        isAdmin: action.isAdmin
      }
    default:
      return state
  }
}
