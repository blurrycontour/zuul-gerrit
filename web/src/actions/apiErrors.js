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

export const SERVER_ERROR = 'SERVER_ERROR'
export const USER_ERROR = 'USER_ERROR'
export const ERROR_RESET = 'ERROR_RESET'

export const serverError = error => ({
    type: SERVER_ERROR,
    error: error.response.data.error,
    description: error.response.data.description,
    zuul_request_id: error.response.data.zuul_request_id
})

export const userError = error => ({
    type: USER_ERROR,
    error: error.response.data.error,
    description: error.response.data.description,
    zuul_request_id: null
})

export const apiErrorReset = () => ({
    type: ERROR_RESET
})