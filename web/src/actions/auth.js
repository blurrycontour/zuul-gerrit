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

export const USERMANAGER_CREATE = 'USERMANAGER_CREATE'
export const USERMANAGER_SUCCESS = 'USERMANAGER_SUCCESS'
export const USERMANAGER_FAIL = 'USERMANAGER_FAIL'

export const USER_ACL_REQUEST = 'USER_ACL_REQUEST'
export const USER_ACL_SUCCESS = 'USER_ACL_SUCCESS'
export const USER_ACL_FAIL = 'USER_ACL_FAIL'

export const userManagerCreateRequest = () => ({
    type: USERMANAGER_CREATE
})

function createUserManagerConfigFromJson(json) {
    let tenant = json.info.tenant
    let auth_info = json.info.capabilities.auth
    if (!auth_info) {
        console.log('No auth config')
        return null
    }
    let realm = auth_info.default_realm
    let client_config = auth_info.realms[realm]
    if (client_config.driver === 'OpenIDConnect') {
        let userManagerConfig = {
            client_id: client_config.client_id,
            redirect_uri: API.getHomepageUrl() + 't/' + tenant + '/auth_callback',
            response_type: 'token id_token',
            scope: client_config.scope,
            authority: client_config.authority,
            automaticSilentRenew: false,
            filterProtocolClaims: true,
            loadUserInfo: true,
        }
        return userManagerConfig
    } else {
        console.log('No OpenIDConnect provider found')
        return null
    }
}

const fetchTenantInfoSuccess = json => ({
    type: USERMANAGER_SUCCESS,
    capabilities: json.info.capabilities,
    userManagerConfig: createUserManagerConfigFromJson(json)
})

const fetchTenantInfoFail = error => ({
    type: USERMANAGER_FAIL,
    error
})

export const createUserManagerFromTenant = (tenantName) => (dispatch) => {
    dispatch(userManagerCreateRequest())
    return API.fetchTenantInfo('tenant/' + tenantName + '/')
        .then(response => dispatch(fetchTenantInfoSuccess(response.data)))
        .catch(error => {
            dispatch(fetchTenantInfoFail(error))
        })
}
