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

function getHomepageUrl(url) {
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
  const subDir = [
    '/autohold/',
    '/build/',
    '/buildset/',
    '/job/',
    '/project/',
    '/stream/',
    '/status/',
  ]
  subDir.forEach(path => {
    if (baseUrl.includes(path)) {
      baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf(path) + 1)
    }
  })

  // Remove tenant scope
  if (baseUrl.includes('/t/')) {
    baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf('/t/') + 1)
  }
  if (!baseUrl.endsWith('/')) {
    baseUrl = baseUrl + '/'
  }
  // console.log('Homepage url is ', baseUrl)
  return baseUrl
}

function getZuulUrl() {
  // Return the zuul root api absolute url
  const ZUUL_API = process.env.REACT_APP_ZUUL_API
  let apiUrl

  if (ZUUL_API) {
    // Api url set at build time, use it
    apiUrl = ZUUL_API
  } else {
    // Api url is relative to homepage path
    apiUrl = getHomepageUrl() + 'api/'
  }
  if (!apiUrl.endsWith('/')) {
    apiUrl = apiUrl + '/'
  }
  if (!apiUrl.endsWith('/api/')) {
    apiUrl = apiUrl + 'api/'
  }
  // console.log('Api url is ', apiUrl)
  return apiUrl
}
const apiUrl = getZuulUrl()


function getStreamUrl(apiPrefix) {
  const streamUrl = (apiUrl + apiPrefix)
    .replace(/(http)(s)?:\/\//, 'ws$2://') + 'console-stream'
  // console.log('Stream url is ', streamUrl)
  return streamUrl
}

// Direct APIs
function fetchInfo() {
  return Axios.get(apiUrl + 'info')
}

function fetchComponents() {
  return Axios.get(apiUrl + 'components')
}

function fetchTenantInfo(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'info')
}
function fetchOpenApi() {
  return Axios.get(getHomepageUrl() + 'openapi.yaml')
}
function fetchTenants() {
  return Axios.get(apiUrl + 'tenants')
}
function fetchConfigErrors(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'config-errors')
}
function fetchStatus(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'status')
}
function fetchChangeStatus(apiPrefix, changeId) {
  return Axios.get(apiUrl + apiPrefix + 'status/change/' + changeId)
}
function fetchBuild(apiPrefix, buildId) {
  return Axios.get(apiUrl + apiPrefix + 'build/' + buildId)
}
function fetchBuilds(apiPrefix, queryString) {
  let path = 'builds'
  if (queryString) {
    path += '?' + queryString.slice(1)
  }
  return Axios.get(apiUrl + apiPrefix + path)
}
function fetchBuildset(apiPrefix, buildsetId) {
  return Axios.get(apiUrl + apiPrefix + 'buildset/' + buildsetId)
}
function fetchBuildsets(apiPrefix, queryString) {
  let path = 'buildsets'
  if (queryString) {
    path += '?' + queryString.slice(1)
  }
  return Axios.get(apiUrl + apiPrefix + path)
}
function fetchProject(apiPrefix, projectName) {
  return Axios.get(apiUrl + apiPrefix + 'project/' + projectName)
}
function fetchProjects(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'projects')
}
function fetchJob(apiPrefix, jobName) {
  return Axios.get(apiUrl + apiPrefix + 'job/' + jobName)
}
function fetchJobs(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'jobs')
}
function fetchLabels(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'labels')
}
function fetchNodes(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'nodes')
}
function fetchAutoholds(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'autohold')
}
function fetchAutohold(apiPrefix, requestId) {
  return Axios.get(apiUrl + apiPrefix + 'autohold/' + requestId)
}

// token-protected API
function fetchUserAuthorizations(apiPrefix, token) {
  // Axios.defaults.headers.common['Authorization'] = 'Bearer ' + token
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.get(apiPrefix + 'authorizations')
    .catch(err => { console.log('An error occurred', err) })
  // Axios.defaults.headers.common['Authorization'] = ''
  return res
}

function dequeue(apiPrefix, projectName, pipeline, change, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/dequeue',
    {
      pipeline: pipeline,
      change: change,
    }
  )
  return res
}
function dequeue_ref(apiPrefix, projectName, pipeline, ref, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/dequeue',
    {
      pipeline: pipeline,
      ref: ref,
    }
  )
  return res
}

function enqueue(apiPrefix, projectName, pipeline, change, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/enqueue',
    {
      pipeline: pipeline,
      change: change,
    }
  )
  return res
}
function enqueue_ref(apiPrefix, projectName, pipeline, ref, oldrev, newrev, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/enqueue',
    {
      pipeline: pipeline,
      ref: ref,
      oldrev: oldrev,
      newrev: newrev,
    }
  )
  return res
}
function autohold(apiPrefix, projectName, job, change, ref,
  reason, count, node_hold_expiration, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/autohold',
    {
      change: change,
      job: job,
      ref: ref,
      reason: reason,
      count: count,
      node_hold_expiration: node_hold_expiration,
    }
  )
  return res
}

function autohold_delete(apiPrefix, requestId, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.delete(
    apiPrefix + '/autohold/' + requestId
  )
  return res
}

function promote(apiPrefix, pipeline, changes, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + '/promote',
    {
      pipeline: pipeline,
      changes: changes,
    }
  )
  return res
}


export {
  apiUrl,
  getHomepageUrl,
  getStreamUrl,
  fetchChangeStatus,
  fetchConfigErrors,
  fetchStatus,
  fetchBuild,
  fetchBuilds,
  fetchBuildset,
  fetchBuildsets,
  fetchProject,
  fetchProjects,
  fetchJob,
  fetchJobs,
  fetchLabels,
  fetchNodes,
  fetchOpenApi,
  fetchTenants,
  fetchInfo,
  fetchComponents,
  fetchTenantInfo,
  fetchUserAuthorizations,
  fetchAutoholds,
  fetchAutohold,
  autohold,
  autohold_delete,
  dequeue,
  dequeue_ref,
  enqueue,
  enqueue_ref,
  promote,
}
