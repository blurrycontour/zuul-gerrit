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

const apiUrl = process.env.REACT_APP_ZUUL_API || 'api/'

function getBaseUrl () {
  const state = store.getState()
  if (!state.info.tenant && state.tenant) {
    return apiUrl + 'tenant/' + state.tenant + '/'
  } else {
    return apiUrl
  }
}
function getStreamUrl () {
  const baseUrl = getBaseUrl()
  let absUrl
  if (baseUrl.match(/^https?:\/\//)) {
    // Absolute url, just need to replace the http scheme
    absUrl = baseUrl.replace(/(http)(s)?:\/\//, 'ws$2://')
  } else {
    // relative url, we need to construct the ws url from window.location
    if (window.location.protocol === 'http:') {
      absUrl = "ws://"
    } else {
      absUrl = "wss://"
    }
    absUrl += window.location.host
    if (window.location.pathname) {
      // Add sub-path
      const dirName = window.location.pathname
            .replace(/\\/g, '/').replace(/\/[^/]*$/, '')
      if (dirName) {
        absUrl += "/" + dirName
      }
    }
    absUrl += '/' + baseUrl
  }
  return absUrl + "console-stream"
}

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
  return Axios.get(getBaseUrl() + 'status')
}
function fetchBuilds (queryString) {
  let url = getBaseUrl() + 'builds'
  if (queryString) {
    url += "?" + queryString.slice(1)
  }
  return Axios.get(url)
}
function fetchJobs () {
  return Axios.get(getBaseUrl() + 'jobs')
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
