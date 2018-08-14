/* global process, Promise, window */
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

import Axios from 'axios'
import { store } from './reducers'

function getZuulUrl () {
  // Return the zuul root api absolute url
  const ZUUL_API = process.env.REACT_APP_ZUUL_API
  let apiUrl

  if (ZUUL_API) {
    // Api url set at build time, use it
    apiUrl = ZUUL_API
  } else {
    // Discover Api url from href
    apiUrl = window.location.href.replace(/\\/g, '/').replace(/\/[^/]*$/, '')
    if (apiUrl.includes('?')) {
      // Remove any query strings
      apiUrl = apiUrl.slice(0, apiUrl.lastIndexOf('?'))
    }
    if (apiUrl.includes('/#/')) {
      // Remove any hash anchor
      apiUrl = apiUrl.slice(0, apiUrl.lastIndexOf('/#/') + 1)
    }
    if (apiUrl.includes('/t/')) {
      // Remove tenant scope
      apiUrl = apiUrl.slice(0, apiUrl.lastIndexOf('/t/') + 1)
    }
  }
  if (! apiUrl.endsWith('/')) {
    apiUrl = apiUrl + '/'
  }
  if (! apiUrl.endsWith('/api/')) {
    apiUrl = apiUrl + 'api/'
  }
  //console.log("Api url is ", apiUrl)
  return apiUrl
}
const apiUrl = getZuulUrl()

function getTenantUrl () {
  // Return the current tenant scoped url
  const state = store.getState()
  let tenantUrl
  if (!state.info.tenant) {
    tenantUrl = apiUrl + 'tenant/' + state.tenant + '/'
  } else {
    tenantUrl = apiUrl
  }
  //console.log("Tenant url is ", tenantUrl)
  return tenantUrl
}
function getStreamUrl () {
  const streamUrl = getTenantUrl()
        .replace(/(http)(s)?:\/\//, 'ws$2://') + 'console-stream'
  //console.log("Stream url is ", streamUrl)
  return streamUrl
}

// Create fake loading time
function sleeper (ms) {
  return function (x) {
    return new Promise(resolve => setTimeout(() => resolve(x), ms))
  }
}

// Direct APIs
function fetchTenants () {
  return Axios.get(apiUrl + 'tenants')
}
function fetchStatus () {
  return Axios.get(getTenantUrl() + 'status')
}
function fetchBuilds (queryString) {
  let url = getTenantUrl() + 'builds'
  if (queryString) {
    url += "?" + queryString.slice(1)
  }
  return Axios.get(url)
}
function fetchJobs () {
  return Axios.get(getTenantUrl() + 'jobs')
}

// Reducer actions
export const fetchInfoSuccess = (info) => {
  return {
    type: 'FETCH_INFO_SUCCESS',
    info
  }
}

function fetchInfo () {
  return (dispatch) => {
    return Axios.get(apiUrl + 'info')
      .then(sleeper(2)).then(response => {
        dispatch(fetchInfoSuccess(response.data.info))
      })
      .catch(error => {
        throw (error)
      })
  }
}

export {
  getStreamUrl, fetchStatus, fetchBuilds, fetchJobs, fetchTenants, fetchInfo
}
