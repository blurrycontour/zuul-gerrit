// Copyright 2018 Red Hat, Inc
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

// Redux store enable to share global variables through state
// To update the store, use a reducer and dispatch method,
// see the App.setTenant method
//
// The store contains:
//   info: the info object, tenant is set when white-label api
//   tenant: the current tenant name, only used with multi-tenant api

import { applyMiddleware, createStore, combineReducers } from 'redux'
import thunk from 'redux-thunk'

import { fetchInfo } from './api'

const infoReducer = (state = {}, action) => {
  switch (action.type) {
    case 'FETCH_INFO_SUCCESS':
      return action.info
    case 'RESET':
      return {}
    default:
      return state
  }
}

const tenantReducer = (state = '', action) => {
  switch (action.type) {
    case 'SET_TENANT':
      return action.name
  case 'RESET':
      return ''
    default:
      return state
  }
}

const reducers = combineReducers({
  info: infoReducer,
  tenant: tenantReducer
})

const store = createStore(reducers, applyMiddleware(thunk))

// Reducer actions
export const fetchInfoSuccess = (info) => {
  return {
    type: 'FETCH_INFO_SUCCESS',
    info
  }
}

function fetchInfoAction () {
  return (dispatch) => {
    return fetchInfo().then(response => {
        dispatch(fetchInfoSuccess(response.data.info))
      })
      .catch(error => {
        throw (error)
      })
  }
}

export { store, fetchInfoAction }
