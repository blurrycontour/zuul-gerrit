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


import * as API from '../api'
import { USER_ACL_FAIL, USER_ACL_REQUEST, USER_ACL_SUCCESS } from './auth'

export const USER_LOGGED_IN = 'USER_LOGGED_IN'
export const USER_LOGGED_OUT = 'USER_LOGGED_OUT'
export const USER_IN_LOCALSTORAGE = 'USER_IN_LOCALSTORAGE'

// Access tokens are not necessary JWTs (Google OAUTH uses a custom format)
// check the access token, if it isn't a JWT, use the ID token

export function getToken(user) {
  try {
    JSON.parse(atob(user.access_token.split('.')[1]))
    return user.access_token
  } catch (e) {
    return user.id_token
  }
}

export const fetchUserACLRequest = () => ({
  type: USER_ACL_REQUEST
})

export const userLoggedIn = (user, tenant) => (dispatch) => {
  let tkn = getToken(user)
  dispatch({
    type: USER_LOGGED_IN,
    user: user,
    token: tkn,
  })
  dispatch(fetchUserACL(tenant, tkn))
}

export const userLoggingOut = (userManager) => (dispatch) => {
  userManager.removeUser()
  dispatch({
    type: USER_LOGGED_OUT
  })
}

export const userInStore = (user, tenant) => (dispatch) => {
  let tkn = getToken(user)
  dispatch({
    type: USER_IN_LOCALSTORAGE,
    user: user,
    token: tkn,
  })
  dispatch(fetchUserACL(tenant, tkn))
}

const fetchUserACLSuccess = (json) => ({
  type: USER_ACL_SUCCESS,
  isAdmin: json.zuul.admin,
  scope: json.zuul.scope,
})

const fetchUserACLFail = error => ({
  type: USER_ACL_FAIL,
  error
})

export const fetchUserACL = (tenant, token) => (dispatch) => {
  dispatch(fetchUserACLRequest())
  let apiPrefix = 'tenant/' + tenant + '/'
  return API.fetchUserAuthorizations(apiPrefix, token)
    .then(response => dispatch(fetchUserACLSuccess(response.data)))
    .catch(error => {
      dispatch(fetchUserACLFail(error))
    })
}
