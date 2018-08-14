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

function getHomepageUrl (url) {
  //
  // Discover serving location from href.
  //
  // This is only needed for sub-directory serving.
  // Serving the application from '/' may simply default to '/'
  //
  // Note that this is not enough for sub-directory serving,
  // The static files location also needs to be adapted with the 'homepage'
  // settings of the package.json file.
  //
  // This homepage url is used for the Router and Link resolution logic
  //
  let baseUrl
  if (url) {
    baseUrl = url
  } else {
    baseUrl = window.location.href
  }
  // Get dirname of the current url
  baseUrl = baseUrl.replace(/\\/g, '/').replace(/\/[^/]*$/, '/')

  // Remove any query strings
  if (baseUrl.includes('?')) {
    baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf('?'))
  }
  // Remove any hash anchor
  if (baseUrl.includes('/#')) {
    baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf('/#') + 1)
  }

  // Remove known sub-path
  const subDir = ['/job/', '/project/', '/stream/']
  subDir.forEach(path => {
    if (baseUrl.includes(path)) {
      baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf(path) + 1)
    }
  })

  // Remove tenant scope
  if (baseUrl.includes('/t/')) {
    baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf('/t/') + 1)
  }
  if (! baseUrl.endsWith('/')) {
    baseUrl = baseUrl + '/'
  }
  // console.log("Homepage url is ", baseUrl)
  return baseUrl
}
function getZuulUrl () {
  // Return the zuul root api absolute url
  const ZUUL_API = process.env.REACT_APP_ZUUL_API
  let apiUrl

  if (ZUUL_API) {
    // Api url set at build time, use it
    apiUrl = ZUUL_API
  } else {
    // Api url is relative to homepage path
    apiUrl = getHomepageUrl () + 'api/'
  }
  if (! apiUrl.endsWith('/')) {
    apiUrl = apiUrl + '/'
  }
  if (! apiUrl.endsWith('/api/')) {
    apiUrl = apiUrl + 'api/'
  }
  // console.log("Api url is ", apiUrl)
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
  // console.log("Tenant url is ", tenantUrl)
  return tenantUrl
}
function getStreamUrl () {
  const streamUrl = getTenantUrl()
        .replace(/(http)(s)?:\/\//, 'ws$2://') + 'console-stream'
  // console.log("Stream url is ", streamUrl)
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
    return Axios.get(apiUrl + 'info').then(response => {
        dispatch(fetchInfoSuccess(response.data.info))
      })
      .catch(error => {
        throw (error)
      })
  }
}

export {
  getHomepageUrl, getStreamUrl,
  fetchStatus, fetchBuilds, fetchJobs, fetchTenants, fetchInfo
}
