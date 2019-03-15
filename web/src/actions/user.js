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


import Keycloak from 'keycloak-js'

export const USER_LOGIN_REQUEST = 'USER_LOGIN_REQUEST'
export const USER_LOGIN_SUCCESS = 'USER_LOGIN_SUCCESS'
export const USER_LOGIN_FAIL = 'USER_LOGIN_FAIL'
export const USER_LOGOUT = 'USER_LOGOUT'

export const loginRequest = () => ({
    type: USER_LOGIN_REQUEST
})

export const loginSuccess = kc => ({
    type: USER_LOGIN_SUCCESS,
    kc: kc
})

export const loginFail = error => ({
    type: USER_LOGIN_FAIL,
    error
})

export const logout = () => ({
    type: USER_LOGOUT
})


const login = () => dispatch => {
    dispatch(loginRequest())
    const keycloak = Keycloak("/keycloak.json")
    keycloak.init({ onLoad: 'login-required' })
        .success(authenticated => {
            console.log('success!')
            console.log(keycloak.token)
            dispatch(loginSuccess(keycloak))})
        .error(err => {
            console.log('error!')
            dispatch(loginFail(err))
            alert(err)
            })
}


export const loginIfNeeded = (isAuthenticated) => (dispatch, getState) => {
    if (!isAuthenticated) {
        return dispatch(login())
    }
}
