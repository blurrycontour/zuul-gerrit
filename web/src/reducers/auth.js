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
    USER_LOGIN_REQUEST,
    USER_LOGIN_SUCCESS,
    AUTHZ_FETCH_SUCCESS,
    USER_LOGIN_FAIL,
    USER_LOGOUT,
} from '../actions/auth'

export default (state = {
    token: null,
    tenants: [],
}, action) => {
    switch (action.type) {
        case USER_LOGIN_REQUEST:
            return {
                token: null,
                tenants: []
            }
        case USER_LOGIN_FAIL:
        case USER_LOGOUT:
            return {
                token: null,
                tenants: []
            }
        case USER_LOGIN_SUCCESS:
            return {
                token: action.token,
                tenants: action.tenants,
            }
        case AUTHZ_FETCH_SUCCESS:
            return {
                token: state.token,
                tenants: action.tenants
            }
        default:
            return state
    }
}
