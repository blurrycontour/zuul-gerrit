// Copyright 2022 Red Hat, Inc
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
    USER_ERROR,
    SERVER_ERROR,
    ERROR_RESET
} from '../actions/apiErrors'

/*eslint no-unused-vars: ["error", { "argsIgnorePattern": "^state$" }]*/

export default (state = {}, action) => {
    switch (action.type) {
        case USER_ERROR:
            return {
                type: 'user',
                error: action.error,
                description: action.description,
                zuul_request_id: null,
            }
        case SERVER_ERROR:
            return {
                type: 'server',
                error: action.error,
                description: action.description,
                zuul_request_id: action.zuul_request_id,
            }
        case ERROR_RESET:
        default:
            return {}
    }
}