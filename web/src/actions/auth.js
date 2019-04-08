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

import * as API from '../api'

export const USER_LOGIN_REQUEST = 'USER_LOGIN_REQUEST'
export const USER_LOGIN_SUCCESS = 'USER_LOGIN_SUCCESS'
export const AUTHZ_FETCH_SUCCESS = 'AUTHZ_FETCH_SUCCESS'
export const USER_LOGIN_FAIL = 'USER_LOGIN_FAIL'
export const USER_LOGOUT = 'USER_LOGOUT'

export const loginRequest = () => ({
    type: USER_LOGIN_REQUEST
})

export const loginSuccess = token => ({
    type: USER_LOGIN_SUCCESS,
    token: token,
})

export const AuthZFetchSuccess = tenants => ({
    type: AUTHZ_FETCH_SUCCESS,
    tenants: tenants
})

export const loginFail = error => ({
    type: USER_LOGIN_FAIL,
    error
})

export const logout = () => ({
    type: USER_LOGOUT
})


export const login = (token) => dispatch => {
    return API.fetchUserAuthZ(token)
        .then(response => dispatch(AuthZFetchSuccess(response.data.zuul.admin)))
}
